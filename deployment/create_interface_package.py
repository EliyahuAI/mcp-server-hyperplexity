#!/usr/bin/env python
"""
Script to create and deploy the perplexity-validator-interface AWS Lambda function.
This Lambda provides an API interface for Excel table validation with preview capabilities.
"""
import os
import sys
import shutil
import subprocess
import zipfile
import argparse
import json
import boto3
import time
from pathlib import Path
import base64
import random
import re
import logging
from botocore.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory setup
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
PACKAGE_DIR = SCRIPT_DIR / "interface_package"
OUTPUT_ZIP = SCRIPT_DIR / "interface_lambda_package.zip"

# Lambda configuration for interface function
LAMBDA_CONFIG = {
    "FunctionName": "perplexity-validator-interface",
    "Runtime": "python3.9",
    "Handler": "interface_lambda_function.lambda_handler",
    "Timeout": 900,  # 15 minutes for file uploads and processing
    "MemorySize": 2048,  # Higher memory for file processing
    "Role": "arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7",
    "Environment": {
        "Variables": {
            "S3_CACHE_BUCKET": "perplexity-cache",
            "S3_RESULTS_BUCKET": "perplexity-results",  # Now using independent results bucket
            "VALIDATOR_LAMBDA_NAME": "perplexity-validator"
        }
    },
    "TracingConfig": {
        "Mode": "Active"  # Enable X-Ray tracing for better debugging
    }
}

# API Gateway configuration
API_GATEWAY_CONFIG = {
    "ApiName": "perplexity-validator-api",
    "Description": "API for Excel table validation with preview capabilities",
    "EndpointConfiguration": {
        "types": ["REGIONAL"]
    },
    "BinaryMediaTypes": [
        "application/octet-stream",
        "multipart/form-data",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel"
    ]
}

def clean_directory(dir_path):
    """Remove all contents of a directory."""
    if dir_path.exists():
        try:
            logger.info(f"Cleaning directory: {dir_path}")
            shutil.rmtree(dir_path)
        except PermissionError as e:
            logger.error(f"Permission error when cleaning directory: {e}")
            logger.info("Trying to use a different approach...")
            
            try:
                if os.name == 'nt':  # Windows
                    time.sleep(1)
                    cmd = f'rmdir /S /Q "{dir_path}"'
                    logger.info(f"Running command: {cmd}")
                    os.system(cmd)
                else:
                    subprocess.call(['rm', '-rf', str(dir_path)])
            except Exception as e2:
                logger.error(f"Second attempt failed: {e2}")
                logger.info("Continuing with a new directory name...")
                timestamp = int(time.time())
                global PACKAGE_DIR
                PACKAGE_DIR = dir_path.parent / f"interface_package_{timestamp}"
                dir_path = PACKAGE_DIR
    
    dir_path.parent.mkdir(parents=True, exist_ok=True)
    dir_path.mkdir(exist_ok=True)
    return dir_path

def install_dependencies():
    """Install dependencies to package directory."""
    logger.info(f"Installing interface Lambda dependencies from {SCRIPT_DIR / 'requirements-interface-lambda.txt'}...")
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "-r", str(SCRIPT_DIR / "requirements-interface-lambda.txt"),
                "-t", str(PACKAGE_DIR),
                "--no-cache-dir"
            ])
            logger.info("Dependencies installed successfully.")
            break
        except subprocess.CalledProcessError as e:
            logger.error(f"Error installing dependencies (attempt {attempt}/{max_attempts}): {e}")
            if attempt == max_attempts:
                raise
            logger.info("Retrying in 2 seconds...")
            time.sleep(2)

def copy_source_files():
    """Copy necessary source files for the interface Lambda."""
    logger.info("Copying interface Lambda source files...")
    
    # Files needed for the interface Lambda
    interface_files = [
        "interface_lambda_function.py",  # Main Lambda handler
        "excel_processor.py",  # For Excel file handling
        "perplexity_schema.py",  # Schema definitions
        "prompt_loader.py",  # Prompt loading utilities
        "row_key_utils.py",  # Row key generation utilities
        "lambda_test_json_clean.py",  # Validation history loader
        "email_sender.py",  # Email sending functionality
        "schema_validator_simplified.py",  # Schema validator for primary key determination
    ]
    
    for file_name in interface_files:
        source_file = SRC_DIR / file_name
        if source_file.exists():
            shutil.copy(source_file, PACKAGE_DIR)
            logger.info(f"Copied {file_name}")
        else:
            logger.warning(f"{file_name} not found at {source_file}")
            # Create placeholder only if the main handler is missing
            if file_name == "interface_lambda_function.py":
                logger.info("Creating placeholder interface_lambda_function.py")
                create_placeholder_lambda_handler()
    
    # Copy prompts.yml file
    prompts_yml = SRC_DIR / "prompts.yml"
    if prompts_yml.exists():
        shutil.copy(prompts_yml, PACKAGE_DIR)
        logger.info("Copied prompts.yml")
    else:
        logger.warning(f"prompts.yml not found at {prompts_yml}")
        # Try looking in project root as fallback
        fallback_prompts_yml = PROJECT_DIR / "prompts.yml"
        if fallback_prompts_yml.exists():
            shutil.copy(fallback_prompts_yml, PACKAGE_DIR)
            logger.info("Copied prompts.yml from project root (fallback)")
        else:
            logger.error("prompts.yml not found in either src or project root!")

def create_placeholder_lambda_handler():
    """Create a placeholder Lambda handler for the interface function."""
    handler_content = '''"""
AWS Lambda handler for the perplexity-validator-interface function.
Provides API interface for Excel table validation with preview capabilities.
"""
import json
import boto3
import base64
import logging
from datetime import datetime
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda handler for the perplexity-validator-interface function.
    
    Supports two main workflows:
    1. Normal workflow: Upload files to S3, return immediate download link
    2. Preview workflow: Process first row only, return Markdown table
    """
    try:
        logger.info(f"Received event: {json.dumps(event, default=str)}")
        
        # Parse request
        http_method = event.get('httpMethod', 'POST')
        headers = event.get('headers', {})
        body = event.get('body', '')
        is_base64_encoded = event.get('isBase64Encoded', False)
        
        # Handle CORS preflight
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
                },
                'body': ''
            }
        
        # Parse query parameters
        query_params = event.get('queryStringParameters') or {}
        preview_first_row = query_params.get('preview_first_row', 'false').lower() == 'true'
        max_rows = int(query_params.get('max_rows', '1000'))
        batch_size = int(query_params.get('batch_size', '10'))
        
        logger.info(f"Parameters - preview_first_row: {preview_first_row}, max_rows: {max_rows}, batch_size: {batch_size}")
        
        # Placeholder response for now
        if preview_first_row:
            # Preview mode - return Markdown table
            start_time = time.time()
            
            # Simulate processing time
            time.sleep(0.1)
            
            processing_time = time.time() - start_time
            total_rows = 100  # Placeholder
            estimated_total_time = total_rows * processing_time
            
            markdown_table = """| Field   | Confidence | Value                     |
|---------|------------|--------------------------|
| Name    | HIGH       | John Smith               |
| Email   | MEDIUM     | john.smith@example.com   |
| Phone   | LOW        | (555) 123-4567           |"""
            
            response_body = {
                "status": "preview_completed",
                "markdown_table": markdown_table,
                "total_rows": total_rows,
                "first_row_processing_time": processing_time,
                "estimated_total_processing_time": estimated_total_time
            }
        else:
            # Normal mode - return S3 link
            download_url = "https://example-bucket.s3.amazonaws.com/Still_Processing.zip"
            password = "temp123"
            
            response_body = {
                "status": "processing_started",
                "download_url": download_url,
                "password": password,
                "message": "Processing started. File will be available at the provided URL once complete."
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(response_body)
        }
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }
'''
    
    handler_file = PACKAGE_DIR / "interface_lambda_function.py"
    with open(handler_file, 'w') as f:
        f.write(handler_content)
    logger.info("Created placeholder interface_lambda_function.py")

def create_zip():
    """Create ZIP file for Lambda deployment."""
    logger.info(f"Creating ZIP file: {OUTPUT_ZIP}")
    
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    
    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(PACKAGE_DIR):
            for file in files:
                file_path = Path(root) / file
                arc_name = file_path.relative_to(PACKAGE_DIR)
                zip_file.write(file_path, arc_name)
                logger.debug(f"Added to ZIP: {arc_name}")
    
    logger.info(f"ZIP file created: {OUTPUT_ZIP}")

def deploy_to_lambda(function_name=None, region=None, deploy_api_gateway=True):
    """Deploy the Lambda function and optionally set up API Gateway."""
    function_name = function_name or LAMBDA_CONFIG["FunctionName"]
    region = region or "us-east-1"
    
    logger.info(f"Deploying Lambda function: {function_name}")
    
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        s3_client = boto3.client('s3', region_name=region)
        
        # Get ZIP file size
        zip_size = OUTPUT_ZIP.stat().st_size
        size_mb = zip_size / (1024 * 1024)
        
        # Check if function exists
        function_exists = False
        try:
            lambda_client.get_function(FunctionName=function_name)
            function_exists = True
            logger.info(f"Function {function_name} exists, updating...")
        except lambda_client.exceptions.ResourceNotFoundException:
            logger.info(f"Function {function_name} does not exist, creating...")
        
        # If package is too large (>50MB), upload to S3 first
        if zip_size > 50 * 1024 * 1024:  # 50MB limit
            logger.info(f"Package size ({size_mb:.2f} MB) exceeds 50MB limit. Uploading to S3...")
            
            # Use the cache bucket for deployment packages
            bucket_name = LAMBDA_CONFIG["Environment"]["Variables"]["S3_CACHE_BUCKET"]
            s3_key = f"lambda-packages/{function_name}-{int(time.time())}.zip"
            
            try:
                # Upload to S3
                s3_client.upload_file(str(OUTPUT_ZIP), bucket_name, s3_key)
                logger.info(f"Uploaded package to s3://{bucket_name}/{s3_key}")
                
                # Deploy from S3
                if function_exists:
                    # Update existing function
                    response = lambda_client.update_function_code(
                        FunctionName=function_name,
                        S3Bucket=bucket_name,
                        S3Key=s3_key
                    )
                    logger.info(f"Function code updated: {response['FunctionArn']}")
                    
                    # Wait for the function to be in a ready state before updating configuration
                    logger.info("Waiting for function to be ready for configuration update...")
                    max_wait_time = 300  # 5 minutes
                    wait_interval = 10   # 10 seconds
                    
                    for i in range(int(max_wait_time / wait_interval)):
                        try:
                            function_info = lambda_client.get_function(FunctionName=function_name)
                            state = function_info['Configuration']['State']
                            last_update_status = function_info['Configuration']['LastUpdateStatus']
                            
                            logger.info(f"Function state: {state}, Last update status: {last_update_status}")
                            
                            if state == 'Active' and last_update_status == 'Successful':
                                logger.info("Function is ready for configuration update!")
                                break
                            elif last_update_status == 'Failed':
                                logger.error("Function update failed!")
                                raise Exception("Function code update failed")
                            else:
                                logger.info(f"Function still updating, waiting {wait_interval} seconds...")
                                time.sleep(wait_interval)
                        except Exception as e:
                            if i == int(max_wait_time / wait_interval) - 1:  # Last attempt
                                logger.error(f"Timeout waiting for function to be ready: {e}")
                                raise
                            logger.info(f"Error checking function state (attempt {i+1}), retrying: {e}")
                            time.sleep(wait_interval)
                    
                    # Update configuration with retry logic
                    max_config_retries = 3
                    for retry in range(max_config_retries):
                        try:
                            lambda_client.update_function_configuration(
                                FunctionName=function_name,
                                Runtime=LAMBDA_CONFIG["Runtime"],
                                Handler=LAMBDA_CONFIG["Handler"],
                                Timeout=LAMBDA_CONFIG["Timeout"],
                                MemorySize=LAMBDA_CONFIG["MemorySize"],
                                Environment=LAMBDA_CONFIG["Environment"],
                                TracingConfig=LAMBDA_CONFIG["TracingConfig"]
                            )
                            logger.info("Function configuration updated")
                            break
                        except lambda_client.exceptions.ResourceConflictException as e:
                            if retry < max_config_retries - 1:
                                logger.info(f"Function still updating, waiting before retry {retry+1}/{max_config_retries}...")
                                time.sleep(30)
                            else:
                                logger.error("Max retries reached for configuration update")
                                raise
                else:
                    # Create new function
                    response = lambda_client.create_function(
                        FunctionName=function_name,
                        Runtime=LAMBDA_CONFIG["Runtime"],
                        Role=LAMBDA_CONFIG["Role"],
                        Handler=LAMBDA_CONFIG["Handler"],
                        Code={
                            'S3Bucket': bucket_name,
                            'S3Key': s3_key
                        },
                        Timeout=LAMBDA_CONFIG["Timeout"],
                        MemorySize=LAMBDA_CONFIG["MemorySize"],
                        Environment=LAMBDA_CONFIG["Environment"],
                        TracingConfig=LAMBDA_CONFIG["TracingConfig"]
                    )
                    logger.info(f"Function created: {response['FunctionArn']}")
                
                # Clean up S3 package after deployment
                try:
                    s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
                    logger.info("Cleaned up S3 deployment package")
                except Exception as e:
                    logger.warning(f"Failed to clean up S3 package: {e}")
                
            except Exception as e:
                logger.error(f"Error uploading to S3: {str(e)}")
                raise
        else:
            # Direct upload for smaller packages
            logger.info(f"Package size ({size_mb:.2f} MB) is under 50MB limit. Direct upload...")
            
            # Read ZIP file
            with open(OUTPUT_ZIP, 'rb') as zip_file:
                zip_content = zip_file.read()
            
            if function_exists:
                # Update existing function
                response = lambda_client.update_function_code(
                    FunctionName=function_name,
                    ZipFile=zip_content
                )
                logger.info(f"Function code updated: {response['FunctionArn']}")
                
                # Wait for the function to be in a ready state before updating configuration
                logger.info("Waiting for function to be ready for configuration update...")
                max_wait_time = 300  # 5 minutes
                wait_interval = 10   # 10 seconds
                
                for i in range(int(max_wait_time / wait_interval)):
                    try:
                        function_info = lambda_client.get_function(FunctionName=function_name)
                        state = function_info['Configuration']['State']
                        last_update_status = function_info['Configuration']['LastUpdateStatus']
                        
                        logger.info(f"Function state: {state}, Last update status: {last_update_status}")
                        
                        if state == 'Active' and last_update_status == 'Successful':
                            logger.info("Function is ready for configuration update!")
                            break
                        elif last_update_status == 'Failed':
                            logger.error("Function update failed!")
                            raise Exception("Function code update failed")
                        else:
                            logger.info(f"Function still updating, waiting {wait_interval} seconds...")
                            time.sleep(wait_interval)
                    except Exception as e:
                        if i == int(max_wait_time / wait_interval) - 1:  # Last attempt
                            logger.error(f"Timeout waiting for function to be ready: {e}")
                            raise
                        logger.info(f"Error checking function state (attempt {i+1}), retrying: {e}")
                        time.sleep(wait_interval)
                
                # Update configuration with retry logic
                max_config_retries = 3
                for retry in range(max_config_retries):
                    try:
                        lambda_client.update_function_configuration(
                            FunctionName=function_name,
                            Runtime=LAMBDA_CONFIG["Runtime"],
                            Handler=LAMBDA_CONFIG["Handler"],
                            Timeout=LAMBDA_CONFIG["Timeout"],
                            MemorySize=LAMBDA_CONFIG["MemorySize"],
                            Environment=LAMBDA_CONFIG["Environment"],
                            TracingConfig=LAMBDA_CONFIG["TracingConfig"]
                        )
                        logger.info("Function configuration updated")
                        break
                    except lambda_client.exceptions.ResourceConflictException as e:
                        if retry < max_config_retries - 1:
                            logger.info(f"Function still updating, waiting before retry {retry+1}/{max_config_retries}...")
                            time.sleep(30)
                        else:
                            logger.error("Max retries reached for configuration update")
                            raise
            else:
                # Create new function
                response = lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime=LAMBDA_CONFIG["Runtime"],
                    Role=LAMBDA_CONFIG["Role"],
                    Handler=LAMBDA_CONFIG["Handler"],
                    Code={'ZipFile': zip_content},
                    Timeout=LAMBDA_CONFIG["Timeout"],
                    MemorySize=LAMBDA_CONFIG["MemorySize"],
                    Environment=LAMBDA_CONFIG["Environment"],
                    TracingConfig=LAMBDA_CONFIG["TracingConfig"]
                )
                logger.info(f"Function created: {response['FunctionArn']}")
        
        # Deploy API Gateway if requested
        if deploy_api_gateway:
            api_url = setup_api_gateway(lambda_client, function_name, region)
            if api_url:
                logger.info(f"API Gateway deployed successfully. Endpoint: {api_url}")
                return True, api_url
        
        return True, None
        
    except Exception as e:
        logger.error(f"Error deploying Lambda function: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def setup_api_gateway(lambda_client, function_name, region):
    """Set up API Gateway for the Lambda function."""
    logger.info("Setting up API Gateway...")
    
    try:
        apigateway_client = boto3.client('apigateway', region_name=region)
        
        # Create or find REST API
        api_name = API_GATEWAY_CONFIG["ApiName"]
        
        # Check if API already exists
        apis = apigateway_client.get_rest_apis()
        existing_api = None
        for api in apis['items']:
            if api['name'] == api_name:
                existing_api = api
                break
        
        if existing_api:
            api_id = existing_api['id']
            logger.info(f"Using existing API: {api_id}")
        else:
            # Create new API
            api_response = apigateway_client.create_rest_api(
                name=api_name,
                description=API_GATEWAY_CONFIG["Description"],
                endpointConfiguration=API_GATEWAY_CONFIG["EndpointConfiguration"],
                binaryMediaTypes=API_GATEWAY_CONFIG["BinaryMediaTypes"]
            )
            api_id = api_response['id']
            logger.info(f"Created new API: {api_id}")
        
        # Get root resource
        resources = apigateway_client.get_resources(restApiId=api_id)
        root_resource_id = None
        for resource in resources['items']:
            if resource['path'] == '/':
                root_resource_id = resource['id']
                break
        
        # Create /validate resource
        validate_resource = None
        for resource in resources['items']:
            if resource['path'] == '/validate':
                validate_resource = resource
                break
        
        if not validate_resource:
            validate_response = apigateway_client.create_resource(
                restApiId=api_id,
                parentId=root_resource_id,
                pathPart='validate'
            )
            validate_resource_id = validate_response['id']
            logger.info("Created /validate resource")
        else:
            validate_resource_id = validate_resource['id']
            logger.info("Using existing /validate resource")
        
        # Create POST method
        try:
            apigateway_client.put_method(
                restApiId=api_id,
                resourceId=validate_resource_id,
                httpMethod='POST',
                authorizationType='NONE'
            )
            logger.info("Created POST method")
        except apigateway_client.exceptions.ConflictException:
            logger.info("POST method already exists")
        
        # Create OPTIONS method for CORS
        try:
            apigateway_client.put_method(
                restApiId=api_id,
                resourceId=validate_resource_id,
                httpMethod='OPTIONS',
                authorizationType='NONE'
            )
            logger.info("Created OPTIONS method for CORS")
        except apigateway_client.exceptions.ConflictException:
            logger.info("OPTIONS method already exists")
        
        # Set up Lambda integration for POST
        lambda_arn = f"arn:aws:lambda:{region}:400232868802:function:{function_name}"
        integration_uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
        
        try:
            apigateway_client.put_integration(
                restApiId=api_id,
                resourceId=validate_resource_id,
                httpMethod='POST',
                type='AWS_PROXY',
                integrationHttpMethod='POST',
                uri=integration_uri
            )
            logger.info("Set up Lambda integration for POST")
        except apigateway_client.exceptions.ConflictException:
            logger.info("Lambda integration for POST already exists")
        
        # Set up CORS integration for OPTIONS
        try:
            apigateway_client.put_integration(
                restApiId=api_id,
                resourceId=validate_resource_id,
                httpMethod='OPTIONS',
                type='MOCK',
                requestTemplates={
                    'application/json': '{"statusCode": 200}'
                }
            )
            
            apigateway_client.put_integration_response(
                restApiId=api_id,
                resourceId=validate_resource_id,
                httpMethod='OPTIONS',
                statusCode='200',
                responseParameters={
                    'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                    'method.response.header.Access-Control-Allow-Methods': "'OPTIONS,POST'",
                    'method.response.header.Access-Control-Allow-Origin': "'*'"
                }
            )
            
            apigateway_client.put_method_response(
                restApiId=api_id,
                resourceId=validate_resource_id,
                httpMethod='OPTIONS',
                statusCode='200',
                responseParameters={
                    'method.response.header.Access-Control-Allow-Headers': False,
                    'method.response.header.Access-Control-Allow-Methods': False,
                    'method.response.header.Access-Control-Allow-Origin': False
                }
            )
            logger.info("Set up CORS integration for OPTIONS")
        except apigateway_client.exceptions.ConflictException:
            logger.info("CORS integration already exists")
        
        # Add Lambda permission for API Gateway
        try:
            lambda_client.add_permission(
                FunctionName=function_name,
                StatementId=f'apigateway-invoke-{int(time.time())}',
                Action='lambda:InvokeFunction',
                Principal='apigateway.amazonaws.com',
                SourceArn=f"arn:aws:execute-api:{region}:400232868802:{api_id}/*/*"
            )
            logger.info("Added Lambda permission for API Gateway")
        except lambda_client.exceptions.ResourceConflictException:
            logger.info("Lambda permission already exists")
        
        # Deploy API
        deployment_response = apigateway_client.create_deployment(
            restApiId=api_id,
            stageName='prod',
            description='Production deployment for perplexity validator interface'
        )
        logger.info("Deployed API to 'prod' stage")
        
        # Return API URL
        api_url = f"https://{api_id}.execute-api.{region}.amazonaws.com/prod/validate"
        return api_url
        
    except Exception as e:
        logger.error(f"Error setting up API Gateway: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def test_api_endpoint(api_url):
    """Test the deployed API endpoint."""
    logger.info(f"Testing API endpoint: {api_url}")
    
    try:
        import requests
        
        # Test preview mode
        preview_response = requests.post(
            f"{api_url}?preview_first_row=true",
            headers={'Content-Type': 'application/json'},
            json={'test': 'data'}
        )
        
        logger.info(f"Preview mode test - Status: {preview_response.status_code}")
        logger.info(f"Preview response: {preview_response.text}")
        
        # Test normal mode
        normal_response = requests.post(
            f"{api_url}?preview_first_row=false",
            headers={'Content-Type': 'application/json'},
            json={'test': 'data'}
        )
        
        logger.info(f"Normal mode test - Status: {normal_response.status_code}")
        logger.info(f"Normal response: {normal_response.text}")
        
        return True
        
    except ImportError:
        logger.warning("requests library not available for testing. Install with: pip install requests")
        return False
    except Exception as e:
        logger.error(f"Error testing API endpoint: {str(e)}")
        return False

def main():
    """Main function."""
    global PACKAGE_DIR
    
    parser = argparse.ArgumentParser(description='Create and deploy AWS Lambda interface package')
    parser.add_argument('--deploy', action='store_true', help='Deploy to AWS Lambda after creating package')
    parser.add_argument('--function-name', help='Lambda function name (default: perplexity-validator-interface)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--no-api-gateway', action='store_true', help='Skip API Gateway setup')
    parser.add_argument('--test-api', action='store_true', help='Test the API endpoint after deployment')
    parser.add_argument('--force-rebuild', action='store_true', help='Force rebuilding the package even if it exists')
    parser.add_argument('--no-rebuild', action='store_true', help='Skip rebuilding the package')
    args = parser.parse_args()
    
    # Get Lambda function name
    function_name = args.function_name or LAMBDA_CONFIG["FunctionName"]
    
    # Check if we need to build the package
    package_exists = OUTPUT_ZIP.exists()
    
    if package_exists and not args.force_rebuild:
        if args.no_rebuild:
            build_package = False
        else:
            build_package = not input("Package already exists. Skip rebuilding? (y/N): ").lower().startswith('y')
    else:
        build_package = True
    
    if build_package:
        logger.info("Creating interface Lambda deployment package...")
        
        try:
            # Create package directory
            PACKAGE_DIR.parent.mkdir(parents=True, exist_ok=True)
            
            # Clean and create package directory
            package_dir = clean_directory(PACKAGE_DIR)
            PACKAGE_DIR = package_dir
            
            logger.info(f"Using package directory: {PACKAGE_DIR}")
            
            # Install dependencies
            install_dependencies()
            
            # Copy source files
            copy_source_files()
            
            # Create ZIP file
            create_zip()
            
            # Get ZIP file size
            size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
            logger.info(f"Done! Package size: {size_mb:.2f} MB")
            logger.info(f"Interface Lambda package created at: {OUTPUT_ZIP}")
        except Exception as e:
            logger.error(f"Error creating Lambda package: {str(e)}")
            import traceback
            traceback.print_exc()
            if not OUTPUT_ZIP.exists():
                logger.error("Failed to create package. Cannot continue with deployment.")
                return 1
    else:
        logger.info(f"Using existing package: {OUTPUT_ZIP}")
    
    # Deploy if requested
    if args.deploy:
        try:
            deploy_api_gateway = not args.no_api_gateway
            success, api_url = deploy_to_lambda(
                args.function_name,
                args.region,
                deploy_api_gateway
            )
            
            if not success:
                return 1
            
            if api_url and args.test_api:
                logger.info("Testing API endpoint...")
                test_api_endpoint(api_url)
            
        except Exception as e:
            logger.error(f"Error during deployment: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1
    else:
        logger.info("\nTo deploy to AWS Lambda with API Gateway, use:")
        logger.info(f"python {__file__} --deploy [--test-api]")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 