"""
Handles demo-related actions for new users.
"""
import logging
import json
import os
import boto3
from typing import Dict, List, Optional
from botocore.exceptions import ClientError

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# S3 client
s3_client = boto3.client('s3')

def get_available_demos() -> List[Dict]:
    """
    Get list of available demos from S3 demos folder.

    Returns:
        List of demo objects with metadata
    """
    try:
        bucket_name = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
        demos_prefix = 'demos/'

        # List all objects in demos/ folder
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=demos_prefix,
            Delimiter='/'
        )

        # Get demo folder names
        demo_folders = []
        if 'CommonPrefixes' in response:
            demo_folders = [prefix['Prefix'] for prefix in response['CommonPrefixes']]

        demos = []
        for folder_prefix in demo_folders:
            # Extract demo name from prefix (demos/demo_name/)
            demo_name = folder_prefix.rstrip('/').split('/')[-1]

            # Get demo metadata
            demo_metadata = get_demo_metadata(bucket_name, demo_name)
            if demo_metadata:
                demos.append(demo_metadata)

        return demos

    except Exception as e:
        logger.error(f"Error getting available demos: {e}")
        return []

def get_demo_metadata(bucket_name: str, demo_name: str) -> Optional[Dict]:
    """
    Get metadata for a specific demo.

    Args:
        bucket_name: S3 bucket name
        demo_name: Name of the demo folder

    Returns:
        Demo metadata dict or None if invalid
    """
    try:
        demo_prefix = f'demos/{demo_name}/'

        # List files in demo folder
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=demo_prefix
        )

        if 'Contents' not in response:
            logger.warning(f"Demo folder {demo_name} is empty")
            return None

        files = {obj['Key'].split('/')[-1]: obj['Key'] for obj in response['Contents']}

        # Find required files
        data_file = None
        config_file = None
        description_file = None

        for filename, s3_key in files.items():
            if filename.lower().endswith(('.xlsx', '.xls', '.csv')):
                data_file = {'name': filename, 's3_key': s3_key}
            elif filename.lower().endswith('.json'):
                config_file = {'name': filename, 's3_key': s3_key}
            elif filename.lower().endswith('.md'):
                description_file = {'name': filename, 's3_key': s3_key}

        # Validate required files exist
        if not all([data_file, config_file, description_file]):
            logger.warning(f"Demo {demo_name} missing required files")
            return None

        # Get description content
        description_content = get_description_content(bucket_name, description_file['s3_key'])

        # Parse display name and description from markdown
        display_name = demo_name.replace('_', ' ').title()
        description = "No description available"

        if description_content:
            lines = description_content.strip().split('\n')
            # Look for title in first heading or bold text
            for line in lines:
                if line.startswith('# '):
                    display_name = line[2:].strip()
                    break
                elif line.strip().startswith('**') and line.strip().endswith('**'):
                    # Handle **Title** format
                    display_name = line.strip()[2:-2].strip()
                    break

            # Get description (only first paragraph after heading/title)
            desc_lines = []
            skip_first_heading = False
            in_first_paragraph = False

            for line in lines:
                # Skip heading line (either # or **)
                if (line.startswith('# ') or (line.strip().startswith('**') and line.strip().endswith('**'))) and not skip_first_heading:
                    skip_first_heading = True
                    continue

                if skip_first_heading:
                    # Start collecting the first paragraph
                    if line.strip():  # Non-empty line
                        if not in_first_paragraph:
                            in_first_paragraph = True
                        desc_lines.append(line)
                    elif in_first_paragraph:
                        # Empty line after paragraph content - stop here
                        break

            if desc_lines:
                description = '\n'.join(desc_lines).strip()

        return {
            'name': demo_name,
            'display_name': display_name,
            'description': description,
            'data_file': data_file,
            'config_file': config_file,
            'description_file': description_file
        }

    except Exception as e:
        logger.error(f"Error getting demo metadata for {demo_name}: {e}")
        return None

def get_description_content(bucket_name: str, s3_key: str) -> Optional[str]:
    """Get content of description markdown file from S3."""
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        return content
    except Exception as e:
        logger.error(f"Error reading description file {s3_key}: {e}")
        return None

def copy_demo_to_session(demo_name: str, email: str, old_session_id: str) -> Dict:
    """
    Copy demo files to user's NEW session folder (demos get fresh session IDs).

    Args:
        demo_name: Name of the demo to copy
        email: User's email
        old_session_id: Previous session ID (unused, demos get new sessions)

    Returns:
        Result dict with success status, file info, and new session ID
    """
    try:
        import uuid
        from datetime import datetime

        bucket_name = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')

        # Get demo metadata
        demo_metadata = get_demo_metadata(bucket_name, demo_name)
        if not demo_metadata:
            return {
                'success': False,
                'error': f'Demo {demo_name} not found or invalid'
            }

        # Generate NEW session ID for demo (use standard session format)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        new_session_id = f"session_demo_{timestamp}_{unique_id}"

        # Determine NEW session folder path using UnifiedS3Manager for consistency
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        storage_manager = UnifiedS3Manager()
        session_prefix = storage_manager.get_session_path(email, new_session_id)

        # Copy data file with _input suffix for consistency with standard pattern
        data_source_key = demo_metadata['data_file']['s3_key']
        original_filename = demo_metadata['data_file']['name']

        # Add _input suffix to filename
        name_parts = original_filename.rsplit('.', 1)
        if len(name_parts) == 2:
            base_name, extension = name_parts
            input_filename = f"{base_name}_input.{extension}"
        else:
            input_filename = f"{original_filename}_input"

        data_dest_key = f"{session_prefix}{input_filename}"

        s3_client.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': data_source_key},
            Key=data_dest_key
        )

        # Read config content from source
        config_source_key = demo_metadata['config_file']['s3_key']
        config_response = s3_client.get_object(Bucket=bucket_name, Key=config_source_key)
        config_content = json.loads(config_response['Body'].read().decode('utf-8'))

        # Use proper versioning system to store config (this creates config_v1_demo.json)

        config_result = storage_manager.store_config_file(
            email=email,
            session_id=new_session_id,
            config_data=config_content,
            version=1,
            source='demo',
            description=f"Demo configuration for {demo_metadata['display_name']}",
            original_name=f"demo_{demo_name}_v1"
        )

        if not config_result['success']:
            raise Exception(f"Failed to store demo config: {config_result.get('error')}")

        config_dest_key = config_result['s3_key']

        # Create session_info.json file so the system can find the Excel file
        session_info = {
            "session_id": new_session_id,
            "created": datetime.now().isoformat(),
            "email": email,
            "table_name": demo_metadata['display_name'],
            "table_path": data_dest_key,  # Path to the Excel file
            "current_version": 1,
            "last_updated": datetime.now().isoformat(),
            "versions": {
                "1": {
                    "version": 1,
                    "config": {
                        "config_id": config_result.get('config_id'),  # Use the proper config_id generated by versioning
                        "config_path": config_dest_key,
                        "created": datetime.now().isoformat(),
                        "source": "demo",
                        "description": f"Demo configuration for {demo_metadata['display_name']}"
                    }
                }
            }
        }

        # Save session_info.json
        session_info_key = f"{session_prefix}session_info.json"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=session_info_key,
            Body=json.dumps(session_info, indent=2),
            ContentType='application/json'
        )

        logger.info(f"Successfully copied demo {demo_name} to NEW session {new_session_id} with session_info.json")

        return {
            'success': True,
            'session_id': new_session_id,  # Return new session ID
            'demo': demo_metadata,
            'files': {
                'data_file': {
                    'name': input_filename,  # Use the new filename with _input suffix
                    'original_name': original_filename,  # Preserve original name for reference
                    's3_key': data_dest_key
                },
                'config_file': {
                    'name': demo_metadata['config_file']['name'],
                    's3_key': config_dest_key
                }
            },
            'config_data': config_content
        }

    except Exception as e:
        logger.error(f"Error copying demo {demo_name} to session: {e}")
        return {
            'success': False,
            'error': f'Failed to copy demo: {str(e)}'
        }

def clear_user_history_for_testing(email: str) -> Dict:
    """
    TESTING ONLY: Clear user's validation history to test new user flow.

    Args:
        email: User's email address

    Returns:
        Result dict with success status
    """
    try:
        import boto3
        from botocore.exceptions import ClientError

        # Only allow in non-production environments
        bucket_name = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
        if bucket_name == 'hyperplexity-storage':  # Production bucket
            return {
                'success': False,
                'error': 'Testing functions disabled in production'
            }

        email = email.lower().strip()

        # Connect to DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('perplexity-validator-runs')

        # Scan for user's runs
        response = table.scan(
            FilterExpression='contains(#email, :email)',
            ExpressionAttributeNames={'#email': 'email'},
            ExpressionAttributeValues={':email': email}
        )

        runs_deleted = 0
        for item in response['Items']:
            try:
                table.delete_item(Key={
                    'session_id': item['session_id'],
                    'run_key': item['run_key']
                })
                runs_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete run {item.get('run_key')}: {e}")

        logger.info(f"[TESTING] Cleared {runs_deleted} validation runs for {email}")

        return {
            'success': True,
            'runs_cleared': runs_deleted,
            'message': f'Cleared {runs_deleted} validation runs for testing'
        }

    except Exception as e:
        logger.error(f"Error clearing user history for testing: {e}")
        return {
            'success': False,
            'error': f'Failed to clear history: {str(e)}'
        }

def handle(request_data, context):
    """
    Handle demo-related requests.

    Supported actions:
    - listDemos: Get available demos
    - selectDemo: Copy demo to user session
    - clearUserHistoryForTesting: Clear user validation history (testing only)
    """
    action = request_data.get('action')

    try:
        if action == 'listDemos':
            demos = get_available_demos()
            return create_response(200, {
                'success': True,
                'demos': demos
            })

        elif action == 'selectDemo':
            demo_name = request_data.get('demo_name', '').strip()
            email = request_data.get('email', '').strip()
            session_id = request_data.get('session_id', '').strip()  # Optional for demos

            if not all([demo_name, email]):
                return create_response(400, {
                    'success': False,
                    'error': 'Missing required parameters: demo_name, email'
                })

            result = copy_demo_to_session(demo_name, email, session_id)
            status_code = 200 if result['success'] else 400
            return create_response(status_code, result)

        elif action == 'clearUserHistoryForTesting':
            email = request_data.get('email', '').strip()

            if not email:
                return create_response(400, {
                    'success': False,
                    'error': 'Missing required parameter: email'
                })

            result = clear_user_history_for_testing(email)
            status_code = 200 if result['success'] else 400
            return create_response(status_code, result)

        else:
            return create_response(400, {
                'success': False,
                'error': f'Unknown demo action: {action}'
            })

    except Exception as e:
        logger.error(f"Error handling demo action '{action}': {e}")
        return create_response(500, {
            'success': False,
            'error': 'Internal server error'
        })