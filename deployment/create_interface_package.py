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
import requests
from botocore.config import Config
from botocore.exceptions import ClientError
import asyncio

# Optional websockets import - will be handled in the test function
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

# Add project root to sys.path to allow for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import environment configuration helper
from environment_config import apply_environment_to_lambda_config, apply_environment_to_api_gateway_config, print_environment_info, load_environment_config

# Directory setup
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
LAMBDA_SRC_DIR = SRC_DIR / "lambdas" / "interface"
SHARED_SRC_DIR = SRC_DIR / "shared"
PACKAGE_DIR = SCRIPT_DIR / "interface_package"
OUTPUT_ZIP = SCRIPT_DIR / "interface_lambda_package.zip"

# Lambda configuration for interface function
LAMBDA_CONFIG = {
    "FunctionName": "perplexity-validator-interface",
    "Runtime": "python3.9",
    "Handler": "interface_lambda_function.lambda_handler", # This will be created in the package root
    "Timeout": 900,  # 15 minutes for file uploads and processing
    "MemorySize": 128,  # Lightweight mode: API routing only (background Lambda uses 512MB)
    "Role": "arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7",
    "Environment": {
        "Variables": {
            "S3_UNIFIED_BUCKET": "hyperplexity-storage",  # Unified bucket for all storage
            "S3_DOWNLOAD_BUCKET": "hyperplexity-storage", # Use downloads/ folder in unified bucket
            "VALIDATOR_LAMBDA_NAME": "perplexity-validator",
            "CONFIG_LAMBDA_NAME": "perplexity-validator-config",
            # Legacy variables for compatibility during transition
            "S3_CACHE_BUCKET": "hyperplexity-storage",
            "S3_RESULTS_BUCKET": "hyperplexity-storage",
            "S3_CONFIG_BUCKET": "hyperplexity-storage",
            # Smart Delegation System SQS Queue Names (will be converted to URLs during deployment)
            "SQS_ASYNC_QUEUE_NAME": "perplexity-validator-async-queue", # Environment-specific queue names will be applied
            "SQS_COMPLETION_QUEUE_NAME": "perplexity-validator-completion-queue", # Environment-specific queue names will be applied
            "MAX_SYNC_INVOCATION_TIME": "10.0",  # Jobs longer than 10 minutes use async delegation
            "VALIDATOR_SAFETY_BUFFER": "3.0"
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

WEBSOCKET_LAMBDA_CONFIG = {
    "FunctionName": "perplexity-validator-ws-handler",
    "Runtime": "python3.9",
    "Handler": "websocket_handler.handle",
    "Timeout": 60,
    "MemorySize": 128,
    "Role": "arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7",
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

def install_dependencies(mode='unified'):
    """Install dependencies to package directory based on deployment mode."""
    # Choose requirements file based on mode
    if mode == 'lightweight':
        requirements_file = SCRIPT_DIR / 'requirements-interface-lightweight.txt'
        logger.info(f"Installing LIGHTWEIGHT Lambda dependencies (minimal) from {requirements_file}...")
        logger.info("Skipping heavy deps: PyMuPDF, openpyxl, xlsxwriter, aioboto3, aiohttp")
    else:
        requirements_file = SCRIPT_DIR / 'requirements-interface-lambda.txt'
        logger.info(f"Installing FULL Lambda dependencies from {requirements_file}...")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            # Install dependencies for Lambda Linux environment (Python 3.9 on manylinux2014_x86_64)
            # When using platform constraints, pip requires BOTH --only-binary=:all: AND --no-binary=:none:
            # This ensures all packages get correct Linux manylinux wheels for the Lambda runtime
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "-r", str(requirements_file),
                "-t", str(PACKAGE_DIR),
                "--platform", "manylinux2014_x86_64",
                "--implementation", "cp",
                "--python-version", "3.9",
                "--only-binary", ":all:",
                "--no-binary", ":none:",
                "--upgrade",
                "--no-cache-dir",
                "--ignore-installed"  # Ignore system packages, force clean install
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
    """Copy necessary source files for the interface Lambda, mimicking the original successful structure."""
    logger.info("Copying interface Lambda source files...")

    # 1. Copy the main Lambda handler file from src root
    main_handler_src = PROJECT_DIR / "src" / "interface_lambda_function.py"
    if main_handler_src.exists():
        shutil.copy(main_handler_src, PACKAGE_DIR / "interface_lambda_function.py")
        logger.info("Copied interface_lambda_function.py as the main handler")
    else:
        logger.error(f"Main handler not found at {main_handler_src}")
        raise FileNotFoundError(f"Main handler not found: {main_handler_src}")

    # 2. Copy the entire 'interface_lambda' package contents into a subdirectory within the package
    shutil.copytree(LAMBDA_SRC_DIR, PACKAGE_DIR / "interface_lambda", dirs_exist_ok=True)
    logger.info("Copied the 'interface_lambda' package directory.")

    # 3. Copy only the necessary shared modules directly into the package root
    shared_modules = [
        "dynamodb_schemas.py",
        "row_key_utils.py",
        "schema_validator_simplified.py",
        "shared_table_parser.py",
        "config_validator.py",
        "ai_api_client.py",
        "email_sender.py",
        "perplexity_schema.py",
        "batch_audit_logger.py",
        "model_config_table.py",
        "web_search_rate_limiter.py",
        "websocket_client.py",
        # QC-enhanced Excel creators
        "excel_report_qc_unified.py",
        "qc_enhanced_excel_report.py",
        "qc_excel_formatter.py"
    ]
    
    for file_name in shared_modules:
        source_file = SHARED_SRC_DIR / file_name
        if source_file.exists():
            shutil.copy(source_file, PACKAGE_DIR)
            logger.info(f"Copied shared module: {file_name}")
        else:
            logger.warning(f"Shared module not found, skipping: {file_name}")
    
    # 4. Copy logo files for PDF receipts
    # Primary: New hyperplexity logo
    new_logo_file = PROJECT_DIR / "frontend" / "hyperplexity-logo-2.png"
    if new_logo_file.exists():
        shutil.copy(new_logo_file, PACKAGE_DIR / "hyperplexity-logo-2.png")
        logger.info("Copied hyperplexity-logo-2.png for PDF receipts")
    else:
        logger.warning(f"New logo file not found at {new_logo_file}")
    
    # Fallback: Legacy Eliyahu logo
    legacy_logo_file = PROJECT_DIR / "src" / "lambdas" / "config" / "EliyahuLogo_NoText_Crop.png"
    if legacy_logo_file.exists():
        shutil.copy(legacy_logo_file, PACKAGE_DIR / "EliyahuLogo_NoText_Crop.png")
        logger.info("Copied EliyahuLogo_NoText_Crop.png as fallback")
    else:
        logger.warning(f"Legacy logo file not found at {legacy_logo_file}")
    
    # Also copy from project root if it exists
    root_logo_file = PROJECT_DIR / "EliyahuLogo_NoText_Crop.png"
    if root_logo_file.exists():
        shutil.copy(root_logo_file, PACKAGE_DIR / "EliyahuLogo_NoText_Crop.png")
        logger.info("Copied EliyahuLogo_NoText_Crop.png from project root")

    # 5. Table Maker prompts and code are in interface_lambda/actions/table_maker/
    # No need to copy root table_maker directory - Lambda uses the local copy
    logger.info("Table Maker prompts/schemas already in interface_lambda/actions/table_maker/ (no root copy needed)")

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

def configure_sqs_event_source_mappings(lambda_client, function_name, region):
    """Configure SQS event source mappings for Smart Delegation System."""
    try:
        logger.info("Configuring SQS event source mappings for Smart Delegation System...")

        # Get AWS account ID for constructing ARNs
        sts_client = boto3.client('sts', region_name=region)
        account_id = sts_client.get_caller_identity()['Account']

        # Define the event source mappings needed for Smart Delegation System
        mappings = []

        # Get environment-specific queue names from lambda config
        async_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_ASYNC_QUEUE_NAME', 'perplexity-validator-async-queue')
        completion_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_COMPLETION_QUEUE_NAME', 'perplexity-validator-completion-queue')

        logger.info(f"[MAPPINGS] Checking event source mappings for function: {function_name}")
        logger.info(f"[MAPPINGS] Async queue: {async_queue_name}")
        logger.info(f"[MAPPINGS] Completion queue: {completion_queue_name}")

        # 1. Interface Lambda should listen to completion queue for async completion processing
        if 'interface' in function_name.lower():
            logger.info(f"[MAPPINGS] Function {function_name} is an interface lambda - adding completion queue mapping")
            mappings.append({
                'queue_name': completion_queue_name,
                'description': 'Async completion processing for interface lambda'
            })

        # 2. Validation Lambda should listen to async queue for async validation requests
        elif 'validator' in function_name.lower() and 'interface' not in function_name.lower():
            mappings.append({
                'queue_name': async_queue_name,
                'description': 'Async validation requests for validation lambda'
            })

        # Configure each mapping
        for mapping in mappings:
            queue_name = mapping['queue_name']
            description = mapping['description']
            queue_arn = f"arn:aws:sqs:{region}:{account_id}:{queue_name}"

            try:
                # Check if mapping already exists
                existing_mappings = lambda_client.list_event_source_mappings(
                    FunctionName=function_name,
                    EventSourceArn=queue_arn
                )

                if existing_mappings['EventSourceMappings']:
                    logger.info(f"[MAPPINGS] SQS event source mapping already exists for {queue_name} -> {function_name}")
                    # Check if it's enabled
                    existing_mapping = existing_mappings['EventSourceMappings'][0]
                    if existing_mapping['State'] != 'Enabled':
                        logger.info(f"Enabling existing event source mapping...")
                        lambda_client.update_event_source_mapping(
                            UUID=existing_mapping['UUID'],
                            Enabled=True
                        )
                        logger.info(f"Event source mapping enabled: {existing_mapping['UUID']}")
                else:
                    # Create new mapping
                    logger.info(f"Creating SQS event source mapping: {description}")
                    response = lambda_client.create_event_source_mapping(
                        EventSourceArn=queue_arn,
                        FunctionName=function_name,
                        BatchSize=1,
                        MaximumBatchingWindowInSeconds=0,
                        Enabled=True
                    )
                    logger.info(f"Created event source mapping: {response['UUID']} ({response['State']})")

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == 'ResourceNotFoundException':
                    logger.warning(f"SQS queue {queue_name} does not exist. Skipping event source mapping.")
                    logger.info(f"Run setup_sqs_queues.py to create the required queues first.")
                else:
                    logger.error(f"Failed to configure event source mapping for {queue_name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error configuring event source mapping for {queue_name}: {e}")

        if not mappings:
            logger.info(f"No SQS event source mappings needed for {function_name}")

    except Exception as e:
        logger.error(f"Error configuring SQS event source mappings: {e}")
        logger.info("This is not critical for basic functionality, continuing deployment...")

def deploy_to_lambda(function_name=None, region=None, deploy_api_gateway=True, stage_name="prod", mode="unified"):
    """Deploy the Lambda function and optionally set up API Gateway."""
    function_name = function_name or LAMBDA_CONFIG["FunctionName"]
    region = region or "us-east-1"
    
    # Get SQS Queue URLs and add them to the Lambda environment variables
    try:
        sqs_client = boto3.client('sqs', region_name=region)
        
        # Use environment-specific queue names from Lambda config if available
        preview_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_PREVIEW_QUEUE_NAME', 'perplexity-validator-preview-queue')
        standard_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_STANDARD_QUEUE_NAME', 'perplexity-validator-standard-queue')
        async_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_ASYNC_QUEUE_NAME', 'perplexity-validator-async-queue')
        completion_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_COMPLETION_QUEUE_NAME', 'perplexity-validator-completion-queue')

        logger.info(f"Looking up SQS queues: preview={preview_queue_name}, standard={standard_queue_name}")
        logger.info(f"Looking up Smart Delegation queues: async={async_queue_name}, completion={completion_queue_name}")

        preview_queue_url = sqs_client.get_queue_url(QueueName=preview_queue_name)['QueueUrl']
        standard_queue_url = sqs_client.get_queue_url(QueueName=standard_queue_name)['QueueUrl']
        async_queue_url = sqs_client.get_queue_url(QueueName=async_queue_name)['QueueUrl']
        completion_queue_url = sqs_client.get_queue_url(QueueName=completion_queue_name)['QueueUrl']

        LAMBDA_CONFIG['Environment']['Variables']['PREVIEW_QUEUE_URL'] = preview_queue_url
        LAMBDA_CONFIG['Environment']['Variables']['STANDARD_QUEUE_URL'] = standard_queue_url
        LAMBDA_CONFIG['Environment']['Variables']['ASYNC_VALIDATOR_QUEUE'] = async_queue_url
        LAMBDA_CONFIG['Environment']['Variables']['INTERFACE_COMPLETION_QUEUE'] = completion_queue_url

        logger.info(f"Found SQS Preview Queue URL: {preview_queue_url}")
        logger.info(f"Found SQS Standard Queue URL: {standard_queue_url}")
        logger.info(f"Found SQS Async Queue URL: {async_queue_url}")
        logger.info(f"Found SQS Completion Queue URL: {completion_queue_url}")
    except Exception as e:
        logger.error(f"Could not retrieve SQS queue URLs. Please ensure queues are created. Error: {e}")
        # Decide if you want to fail deployment or continue without SQS integration
        # For now, we will continue but log a prominent warning.
        logger.warning("Continuing deployment without SQS queue URLs set in environment.")

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
                    
                    # Get existing environment variables to preserve WEBSOCKET_API_URL
                    existing_env_vars = {}
                    try:
                        existing_config = lambda_client.get_function_configuration(FunctionName=function_name)
                        existing_env_vars = existing_config.get('Environment', {}).get('Variables', {})
                        logger.info(f"Existing environment variables: {list(existing_env_vars.keys())}")
                    except Exception as e:
                        logger.warning(f"Could not retrieve existing environment variables: {e}")
                    
                    # Merge existing and new environment variables, prioritizing new ones
                    merged_env_vars = {**existing_env_vars, **LAMBDA_CONFIG["Environment"]["Variables"]}
                    
                    # Update configuration with retry logic
                    max_config_retries = 3
                    for retry in range(max_config_retries):
                        try:
                            update_params = {
                                'FunctionName': function_name,
                                'Runtime': LAMBDA_CONFIG["Runtime"],
                                'Handler': LAMBDA_CONFIG["Handler"],
                                'Timeout': LAMBDA_CONFIG["Timeout"],
                                'MemorySize': LAMBDA_CONFIG["MemorySize"],
                                'Environment': {'Variables': merged_env_vars},
                                'TracingConfig': LAMBDA_CONFIG["TracingConfig"]
                            }
                            if "Layers" in LAMBDA_CONFIG:
                                update_params["Layers"] = LAMBDA_CONFIG["Layers"]
                            
                            lambda_client.update_function_configuration(**update_params)
                            logger.info("Function configuration updated")
                            if 'WEBSOCKET_API_URL' in merged_env_vars:
                                logger.info(f"Preserved WEBSOCKET_API_URL: {merged_env_vars['WEBSOCKET_API_URL']}")
                            # Set log retention policy
                            set_log_retention_policy(function_name, region)
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
                    create_params = {
                        'FunctionName': function_name,
                        'Runtime': LAMBDA_CONFIG["Runtime"],
                        'Role': LAMBDA_CONFIG["Role"],
                        'Handler': LAMBDA_CONFIG["Handler"],
                        'Code': {
                            'S3Bucket': bucket_name,
                            'S3Key': s3_key
                        },
                        'Timeout': LAMBDA_CONFIG["Timeout"],
                        'MemorySize': LAMBDA_CONFIG["MemorySize"],
                        'Environment': LAMBDA_CONFIG["Environment"],
                        'TracingConfig': LAMBDA_CONFIG["TracingConfig"]
                    }
                    if "Layers" in LAMBDA_CONFIG:
                        create_params["Layers"] = LAMBDA_CONFIG["Layers"]
                    
                    response = lambda_client.create_function(**create_params)
                    logger.info(f"Function created: {response['FunctionArn']}")
                    # Set log retention policy
                    set_log_retention_policy(function_name, region)
                
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
                
                # Get existing environment variables to preserve WEBSOCKET_API_URL
                existing_env_vars = {}
                try:
                    existing_config = lambda_client.get_function_configuration(FunctionName=function_name)
                    existing_env_vars = existing_config.get('Environment', {}).get('Variables', {})
                    logger.info(f"Existing environment variables: {list(existing_env_vars.keys())}")
                except Exception as e:
                    logger.warning(f"Could not retrieve existing environment variables: {e}")
                
                # Merge existing and new environment variables, prioritizing new ones
                merged_env_vars = {**existing_env_vars, **LAMBDA_CONFIG["Environment"]["Variables"]}
                
                # Update configuration with retry logic
                max_config_retries = 3
                for retry in range(max_config_retries):
                    try:
                        update_params = {
                            'FunctionName': function_name,
                            'Runtime': LAMBDA_CONFIG["Runtime"],
                            'Handler': LAMBDA_CONFIG["Handler"],
                            'Timeout': LAMBDA_CONFIG["Timeout"],
                            'MemorySize': LAMBDA_CONFIG["MemorySize"],
                            'Environment': {'Variables': merged_env_vars},
                            'TracingConfig': LAMBDA_CONFIG["TracingConfig"]
                        }
                        if "Layers" in LAMBDA_CONFIG:
                            update_params["Layers"] = LAMBDA_CONFIG["Layers"]
                        
                        lambda_client.update_function_configuration(**update_params)
                        logger.info("Function configuration updated")
                        if 'WEBSOCKET_API_URL' in merged_env_vars:
                            logger.info(f"Preserved WEBSOCKET_API_URL: {merged_env_vars['WEBSOCKET_API_URL']}")
                        # Set log retention policy
                        set_log_retention_policy(function_name, region)
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
                create_params = {
                    'FunctionName': function_name,
                    'Runtime': LAMBDA_CONFIG["Runtime"],
                    'Role': LAMBDA_CONFIG["Role"],
                    'Handler': LAMBDA_CONFIG["Handler"],
                    'Code': {'ZipFile': zip_content},
                    'Timeout': LAMBDA_CONFIG["Timeout"],
                    'MemorySize': LAMBDA_CONFIG["MemorySize"],
                    'Environment': LAMBDA_CONFIG["Environment"],
                    'TracingConfig': LAMBDA_CONFIG["TracingConfig"]
                }
                if "Layers" in LAMBDA_CONFIG:
                    create_params["Layers"] = LAMBDA_CONFIG["Layers"]
                
                response = lambda_client.create_function(**create_params)
                logger.info(f"Function created: {response['FunctionArn']}")
                # Set log retention policy
                set_log_retention_policy(function_name, region)
        
        # Configure SQS event source mappings based on deployment mode
        configure_sqs_mappings_for_mode(mode, lambda_client, function_name, region)

        # Deploy API Gateway if requested
        if deploy_api_gateway:
            api_url = setup_api_gateway(lambda_client, function_name, region, stage_name)
            if api_url:
                logger.info(f"API Gateway deployed successfully. Endpoint: {api_url}")
                return True, api_url

        return True, None
        
    except Exception as e:
        logger.error(f"Error deploying Lambda function: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None


def ensure_lambda_permission(lambda_client, function_name, statement_id, source_arn):
    """Ensure the correct API Gateway invocation permission exists by removing old ones first."""
    try:
        # Attempt to remove the permission first to handle outdated SourceArns.
        # This will fail if the permission doesn't exist, which is fine.
        try:
            lambda_client.remove_permission(
                FunctionName=function_name,
                StatementId=statement_id
            )
            logger.info(f"Removed existing permission '{statement_id}' to ensure it's updated.")
        except lambda_client.exceptions.ResourceNotFoundException:
            logger.info(f"Permission '{statement_id}' does not exist, will create it.")
            pass # Permission doesn't exist, no need to remove

        # Add the new/correct permission
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=source_arn
        )
        logger.info(f"Successfully added/updated Lambda permission: {statement_id}")

    except Exception as e:
        logger.error(f"An unexpected error occurred while setting Lambda permission '{statement_id}': {e}")
        # Continue deployment but log the error clearly.
        pass

def setup_api_gateway(lambda_client, function_name, region, stage_name="prod"):
    """Set up API Gateway for the Lambda function with simplified /validate and /status endpoints."""
    logger.info("Setting up simplified API Gateway with Lambda proxy integration...")
    
    try:
        apigateway_client = boto3.client('apigateway', region_name=region)
        account_id = boto3.client('sts').get_caller_identity()['Account']
        api_name = API_GATEWAY_CONFIG["ApiName"]

        # Find or create the REST API
        apis = apigateway_client.get_rest_apis()
        existing_api = next((api for api in apis['items'] if api['name'] == api_name), None)
        
        if existing_api:
            api_id = existing_api['id']
            logger.info(f"Using existing API: {api_id}")
        else:
            api_response = apigateway_client.create_rest_api(
                name=api_name,
                description=API_GATEWAY_CONFIG["Description"],
                endpointConfiguration=API_GATEWAY_CONFIG["EndpointConfiguration"],
                binaryMediaTypes=API_GATEWAY_CONFIG["BinaryMediaTypes"]
            )
            api_id = api_response['id']
            logger.info(f"Created new API: {api_id}")

        # Get root resource ID
        resources = apigateway_client.get_resources(restApiId=api_id)['items']
        root_resource_id = next(res['id'] for res in resources if res['path'] == '/')

        # --- Create /validate Resource and POST Method ---
        validate_resource = next((res for res in resources if res.get('pathPart') == 'validate'), None)
        if not validate_resource:
            validate_resource = apigateway_client.create_resource(restApiId=api_id, parentId=root_resource_id, pathPart='validate')
        validate_resource_id = validate_resource['id']
        
        # --- Create /status and /status/{sessionId} Resources ---
        status_resource = next((res for res in resources if res.get('pathPart') == 'status'), None)
        if not status_resource:
            status_resource = apigateway_client.create_resource(restApiId=api_id, parentId=root_resource_id, pathPart='status')
        status_resource_id = status_resource['id']

        status_session_resource = next((res for res in resources if res.get('pathPart') == '{sessionId}' and res.get('parentId') == status_resource_id), None)
        if not status_session_resource:
            status_session_resource = apigateway_client.create_resource(restApiId=api_id, parentId=status_resource_id, pathPart='{sessionId}')
        status_session_resource_id = status_session_resource['id']
        
        # --- Create /health Resource ---
        health_resource = next((res for res in resources if res.get('pathPart') == 'health'), None)
        if not health_resource:
            health_resource = apigateway_client.create_resource(restApiId=api_id, parentId=root_resource_id, pathPart='health')
        health_resource_id = health_resource['id']

        # --- Create /webhook Resource and /webhook/payment Resource ---
        webhook_resource = next((res for res in resources if res.get('pathPart') == 'webhook'), None)
        if not webhook_resource:
            webhook_resource = apigateway_client.create_resource(restApiId=api_id, parentId=root_resource_id, pathPart='webhook')
        webhook_resource_id = webhook_resource['id']

        webhook_payment_resource = next((res for res in resources if res.get('pathPart') == 'payment' and res.get('parentId') == webhook_resource_id), None)
        if not webhook_payment_resource:
            webhook_payment_resource = apigateway_client.create_resource(restApiId=api_id, parentId=webhook_resource_id, pathPart='payment')
        webhook_payment_resource_id = webhook_payment_resource['id']

        # --- Create /payment Resource and /payment/webhook Resource (alternative path) ---
        payment_resource = next((res for res in resources if res.get('pathPart') == 'payment' and res.get('parentId') == root_resource_id), None)
        if not payment_resource:
            payment_resource = apigateway_client.create_resource(restApiId=api_id, parentId=root_resource_id, pathPart='payment')
        payment_resource_id = payment_resource['id']

        payment_webhook_resource = next((res for res in resources if res.get('pathPart') == 'webhook' and res.get('parentId') == payment_resource_id), None)
        if not payment_webhook_resource:
            payment_webhook_resource = apigateway_client.create_resource(restApiId=api_id, parentId=payment_resource_id, pathPart='webhook')
        payment_webhook_resource_id = payment_webhook_resource['id']

        # --- Define Methods and Integrations ---
        lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{function_name}"
        lambda_integration_uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"

        # List of resources and their methods
        resource_setups = [
            (validate_resource_id, 'POST'),
            (validate_resource_id, 'OPTIONS'),
            (status_session_resource_id, 'GET'),
            (status_session_resource_id, 'OPTIONS'),
            (health_resource_id, 'GET'),
            (health_resource_id, 'OPTIONS'),
            (webhook_payment_resource_id, 'POST'),
            (webhook_payment_resource_id, 'OPTIONS'),
            (payment_webhook_resource_id, 'POST'),
            (payment_webhook_resource_id, 'OPTIONS'),
        ]

        for resource_id, http_method in resource_setups:
            try:
                apigateway_client.put_method(
                    restApiId=api_id,
                    resourceId=resource_id,
                    httpMethod=http_method,
                    authorizationType='NONE'
                )
                apigateway_client.put_integration(
                    restApiId=api_id,
                    resourceId=resource_id,
                    httpMethod=http_method,
                    type='AWS_PROXY',
                    integrationHttpMethod='POST',
                    uri=lambda_integration_uri
                )
                logger.info(f"Set up {http_method} method and integration for resource {resource_id}")
            except apigateway_client.exceptions.ConflictException:
                logger.info(f"{http_method} method and integration already exist for resource {resource_id}")
        
        # Add Lambda permission for the API Gateway
        statement_id = f'apigateway-rest-invoke-{function_name}'
        source_arn = f"arn:aws:execute-api:{region}:{account_id}:{api_id}/*/*/*"
        ensure_lambda_permission(lambda_client, function_name, statement_id, source_arn)

        # Also ensure the Lambda role has S3 delete permissions
        lambda_role_name = LAMBDA_CONFIG['Role'].split('/')[-1]
        iam_client = boto3.client('iam')
        try:
            iam_client.attach_role_policy(
                RoleName=lambda_role_name,
                PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess' # Using a managed policy for simplicity
            )
            logger.info(f"Attached AmazonS3FullAccess policy to role {lambda_role_name} to ensure delete permissions.")
        except iam_client.exceptions.NoSuchEntityException:
            logger.error(f"Lambda execution role not found: {lambda_role_name}")
        except Exception as e:
            logger.warning(f"Could not attach S3 delete policy (may already be attached or permissions issue): {e}")

        # Deploy API
        apigateway_client.create_deployment(restApiId=api_id, stageName=stage_name, description=f'Simplified deployment to {stage_name}')
        logger.info(f"Deployed API to '{stage_name}' stage")
        
        api_url = f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage_name}/validate"
        logger.info(f"API Endpoint: {api_url}")
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

def setup_dynamodb_tables(region="us-east-1"):
    """Set up DynamoDB tables required for email validation and user tracking."""
    logger.info("Setting up DynamoDB tables for email validation and user tracking...")
    
    try:
        # Create the validation runs table
        from src.shared import dynamodb_schemas
        dynamodb_schemas.create_validation_runs_table()
        logger.info("✅ Validation runs table created/verified")
        
        # Create the WebSocket connections table
        dynamodb_schemas.create_websocket_connections_table()
        logger.info("✅ WebSocket connections table created/verified")
        
        # Create account management tables
        try:
            dynamodb_schemas.create_account_transactions_table()
            logger.info("✅ Account transactions table created/verified")
        except Exception as e:
            logger.error(f"Failed to create account transactions table: {e}")
        
        try:
            dynamodb_schemas.create_domain_multipliers_table()
            logger.info("✅ Domain multipliers table created/verified")
        except Exception as e:
            logger.error(f"Failed to create domain multipliers table: {e}")
        
        # Create batch audit table
        try:
            from src.shared.batch_audit_logger import create_batch_audit_table
            create_batch_audit_table()
            logger.info("✅ Batch audit table created/verified")
        except Exception as e:
            logger.error(f"Failed to create batch audit table: {e}")
        
        # Create model config table
        try:
            from src.shared.model_config_table import create_model_config_table, ModelConfigTable
            create_model_config_table()
            logger.info("✅ Model config table created/verified")
            
            # Check if model configurations exist, and populate if empty
            try:
                config_table = ModelConfigTable()
                configs = config_table.list_all_configs()
                
                if not configs:
                    logger.info("📋 Model config table is empty, loading default configurations...")
                    # Try to load from the unified model config CSV
                    import os
                    from pathlib import Path
                    
                    script_dir = Path(__file__).parent.absolute()
                    project_dir = script_dir.parent
                    config_csv_path = project_dir / "src" / "config" / "unified_model_config.csv"
                    
                    if config_csv_path.exists():
                        loaded_count = config_table.load_config_from_csv(str(config_csv_path))
                        if loaded_count > 0:
                            logger.info(f"✅ Loaded {loaded_count} model configurations from {config_csv_path}")
                        else:
                            logger.warning("⚠️ No configurations loaded from CSV file")
                    else:
                        logger.warning(f"⚠️ Model config CSV not found at {config_csv_path}")
                else:
                    logger.info(f"✅ Model config table already has {len(configs)} configurations")
                    
            except Exception as config_load_error:
                logger.error(f"Failed to load model configurations: {config_load_error}")
                # Don't fail the deployment for this
                
        except Exception as e:
            logger.error(f"Failed to create model config table: {e}")
        
        # Define table names using the same pattern as the original code
        user_validation_table = dynamodb_schemas.DynamoDBSchemas.USER_VALIDATION_TABLE
        user_tracking_table = dynamodb_schemas.DynamoDBSchemas.USER_TRACKING_TABLE
        
        # Get DynamoDB client
        dynamodb_client = boto3.client('dynamodb', region_name=region)
        
        # Create user validation table using dynamodb_schemas function
        try:
            dynamodb_schemas.create_user_validation_table()
            logger.info("✅ User validation table created/verified")
        except Exception as e:
            logger.error(f"Failed to create user validation table: {e}")
        
        # Create user tracking table using dynamodb_schemas function
        try:
            dynamodb_schemas.create_user_tracking_table()
            logger.info("✅ User tracking table created/verified")
        except Exception as e:
            logger.error(f"Failed to create user tracking table: {e}")
        
        logger.info("✅ All DynamoDB tables are ready!")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up DynamoDB tables: {e}")
        return False

def setup_sqs_queues(region):
    """Create SQS queues if they don't exist, and ensure correct configuration."""
    logger.info("Setting up SQS queues...")
    try:
        sqs_client = boto3.client('sqs', region_name=region)

        # Get environment-specific queue names from Lambda configuration
        preview_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_PREVIEW_QUEUE_NAME', 'perplexity-validator-preview-queue')
        standard_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_STANDARD_QUEUE_NAME', 'perplexity-validator-standard-queue')

        # Smart Delegation System queues (environment-specific)
        async_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_ASYNC_QUEUE_NAME', 'perplexity-validator-async-queue')
        completion_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_COMPLETION_QUEUE_NAME', 'perplexity-validator-completion-queue')

        # Use 900 seconds (15 minutes) for queue timeout to match Lambda timeout
        queues_to_create = [
            # Legacy queues
            (preview_queue_name, {"VisibilityTimeout": "960", "MessageRetentionPeriod": "345600"}),
            (standard_queue_name, {"VisibilityTimeout": "960", "MessageRetentionPeriod": "345600"}),
            # Smart Delegation System queues
            (async_queue_name, {
                "VisibilityTimeout": "900",           # 15 minutes - match lambda timeout
                "MessageRetentionPeriod": "1209600",  # 14 days - keep messages for retry
                "ReceiveMessageWaitTimeSeconds": "20" # Long polling to reduce API calls
            }),
            (completion_queue_name, {
                "VisibilityTimeout": "900",           # 15 minutes - match lambda timeout
                "MessageRetentionPeriod": "86400",    # 1 day - completion messages should be processed quickly
                "ReceiveMessageWaitTimeSeconds": "20" # Long polling
            })
        ]
        
        for queue_name, attributes in queues_to_create:
            try:
                # Check if queue exists
                queue_url_response = sqs_client.get_queue_url(QueueName=queue_name)
                queue_url = queue_url_response['QueueUrl']
                logger.info(f"SQS queue already exists: {queue_name}")
                
                # Update queue attributes to ensure correct configuration
                try:
                    sqs_client.set_queue_attributes(
                        QueueUrl=queue_url,
                        Attributes=attributes
                    )
                    logger.info(f"Updated queue attributes for: {queue_name}")
                except Exception as attr_error:
                    logger.warning(f"Could not update attributes for {queue_name}: {attr_error}")
                    
            except sqs_client.exceptions.QueueDoesNotExist:
                # Create the queue
                logger.info(f"Creating SQS queue: {queue_name}")
                response = sqs_client.create_queue(
                    QueueName=queue_name,
                    Attributes=attributes
                )
                logger.info(f"Created SQS queue: {response['QueueUrl']}")
            except Exception as e:
                logger.error(f"Error checking/creating queue {queue_name}: {e}")
                return False
        
        logger.info("✅ All SQS queues are ready!")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up SQS queues: {e}")
        return False

def setup_sqs_triggers(lambda_client, function_name, region):
    """Create event source mappings to trigger the Lambda from SQS queues, cleaning up incorrect mappings."""
    logger.info("Setting up SQS triggers for Lambda function...")
    try:
        sqs_client = boto3.client('sqs', region_name=region)
        account_id = boto3.client('sts').get_caller_identity()['Account']

        # Get function ARN
        function_arn = lambda_client.get_function(FunctionName=function_name)['Configuration']['FunctionArn']

        # Get environment-specific queue names from Lambda configuration
        preview_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_PREVIEW_QUEUE_NAME', 'perplexity-validator-preview-queue')
        standard_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_STANDARD_QUEUE_NAME', 'perplexity-validator-standard-queue')
        
        # Get queue ARNs
        preview_queue_arn = f"arn:aws:sqs:{region}:{account_id}:{preview_queue_name}"
        standard_queue_arn = f"arn:aws:sqs:{region}:{account_id}:{standard_queue_name}"
        
        logger.info(f"Setting up triggers for queues: {preview_queue_name}, {standard_queue_name}")
        
        # Check existing mappings
        existing_mappings = lambda_client.list_event_source_mappings(FunctionName=function_name).get('EventSourceMappings', [])
        
        # Get completion queue for Smart Delegation System
        completion_queue_name = LAMBDA_CONFIG['Environment']['Variables'].get('SQS_COMPLETION_QUEUE_NAME', 'perplexity-validator-completion-queue')
        completion_queue_arn = f"arn:aws:sqs:{region}:{account_id}:{completion_queue_name}"

        # Clean up incorrect/old mappings first (but preserve completion queue mapping!)
        target_arns = {preview_queue_arn, standard_queue_arn, completion_queue_arn}
        for mapping in existing_mappings:
            if mapping['EventSourceArn'] not in target_arns:
                logger.info(f"[CLEANUP] Removing incorrect event source mapping: {mapping['EventSourceArn']}")
                try:
                    lambda_client.delete_event_source_mapping(UUID=mapping['UUID'])
                    logger.info(f"[CLEANUP] Deleted mapping UUID: {mapping['UUID']}")
                except Exception as delete_error:
                    logger.warning(f"[CLEANUP] Could not delete mapping {mapping['UUID']}: {delete_error}")
            else:
                logger.info(f"[KEEP] Preserving event source mapping: {mapping['EventSourceArn']}")
        
        # Refresh mappings after cleanup
        existing_mappings = lambda_client.list_event_source_mappings(FunctionName=function_name).get('EventSourceMappings', [])
        existing_arns = {m['EventSourceArn'] for m in existing_mappings}
        
        # Trigger for Standard Queue
        if standard_queue_arn not in existing_arns:
            try:
                lambda_client.create_event_source_mapping(
                    EventSourceArn=standard_queue_arn,
                    FunctionName=function_name,
                    Enabled=True,
                    BatchSize=5
                )
                logger.info("Created SQS trigger for the standard queue.")
            except Exception as e:
                logger.error(f"Failed to create standard queue trigger: {e}")
        else:
            logger.info("SQS trigger for the standard queue already exists.")
            
        # Trigger for Preview Queue
        if preview_queue_arn not in existing_arns:
            try:
                lambda_client.create_event_source_mapping(
                    EventSourceArn=preview_queue_arn,
                    FunctionName=function_name,
                    Enabled=True,
                    BatchSize=1
                )
                logger.info("Created SQS trigger for the preview queue.")
            except Exception as e:
                logger.error(f"Failed to create preview queue trigger: {e}")
        else:
            logger.info("SQS trigger for the preview queue already exists.")
        
        return True
    except Exception as e:
        logger.error(f"Failed to set up SQS triggers: {e}")
        return False

def create_websocket_lambda_package(output_zip_path):
    """Creates a deployment package for the WebSocket handler Lambda, restoring the original working structure."""
    logger.info("Creating WebSocket handler deployment package...")
    package_dir = SCRIPT_DIR / "websocket_package"
    clean_directory(package_dir)
    
    # Revert to the original, successful packaging strategy
    # Copy the handler and its dependency directly into the package root
    shutil.copy(SRC_DIR / "lambdas" / "websocket" / "websocket_handler.py", package_dir)
    shutil.copy(SRC_DIR / "shared" / "dynamodb_schemas.py", package_dir)
    
    # Create the ZIP file
    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(package_dir):
            for file in files:
                file_path = Path(root) / file
                arc_name = file_path.relative_to(package_dir)
                zip_file.write(file_path, arc_name)
    logger.info(f"WebSocket package created at {output_zip_path}")

def deploy_websocket_lambda(zip_path, region):
    """Deploys the WebSocket handler Lambda function."""
    config = WEBSOCKET_LAMBDA_CONFIG
    function_name = "perplexity-validator-ws-handler"
    logger.info(f"Deploying WebSocket Lambda: {function_name}")
    lambda_client = boto3.client('lambda', region_name=region)
    
    with open(zip_path, 'rb') as zip_file:
        zip_content = zip_file.read()

    try:
        lambda_client.get_function(FunctionName=function_name)
        logger.info("WebSocket Lambda exists, updating code...")
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_content,
            Publish=True
        )
        set_log_retention_policy(function_name, region)
        return response
    except lambda_client.exceptions.ResourceNotFoundException:
        logger.info("WebSocket Lambda does not exist, creating...")
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime=config['Runtime'],
            Role=config['Role'],
            Handler=config['Handler'],
            Code={'ZipFile': zip_content},
            Timeout=config['Timeout'],
            MemorySize=config['MemorySize'],
            Publish=True
        )
        set_log_retention_policy(function_name, region)
        return response

def setup_websocket_api(lambda_function_name, region, stage_name="prod"):
    """Creates and configures the WebSocket API in API Gateway."""
    logger.info("Setting up WebSocket API...")
    apigw_client = boto3.client('apigatewayv2', region_name=region)
    lambda_client = boto3.client('lambda', region_name=region)
    account_id = boto3.client('sts').get_caller_identity()['Account']
    api_name = "perplexity-validator-websocket-api"
    
    # Create or get WebSocket API
    apis = apigw_client.get_apis().get('Items', [])
    api = next((a for a in apis if a['Name'] == api_name), None)
    if not api:
        api = apigw_client.create_api(Name=api_name, ProtocolType='WEBSOCKET', RouteSelectionExpression='$request.body.action')
    api_id = api['ApiId']
    api_endpoint = api['ApiEndpoint']

    # Create Lambda integration
    lambda_uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/arn:aws:lambda:{region}:{account_id}:function:{lambda_function_name}/invocations"
    integrations = apigw_client.get_integrations(ApiId=api_id).get('Items', [])
    integration = next((i for i in integrations if i.get('IntegrationUri') == lambda_uri), None)
    if not integration:
        integration = apigw_client.create_integration(ApiId=api_id, IntegrationType='AWS_PROXY', IntegrationUri=lambda_uri, PayloadFormatVersion='1.0')
    integration_id = integration['IntegrationId']

    # Create routes and attach integration
    routes = apigw_client.get_routes(ApiId=api_id).get('Items', [])
    route_keys = ['$connect', '$disconnect', 'subscribe']
    for route_key in route_keys:
        if not any(r['RouteKey'] == route_key for r in routes):
            apigw_client.create_route(ApiId=api_id, RouteKey=route_key, Target=f'integrations/{integration_id}')

    # Create the stage before deploying to it
    try:
        apigw_client.get_stage(ApiId=api_id, StageName=stage_name)
        logger.info(f"Stage '{stage_name}' already exists.")
    except apigw_client.exceptions.NotFoundException:
        apigw_client.create_stage(ApiId=api_id, StageName=stage_name)
        logger.info(f"Created stage '{stage_name}'.")

    # Deploy the API
    apigw_client.create_deployment(ApiId=api_id, StageName=stage_name)

    # Grant API Gateway permission to invoke the Lambda
    statement_id = f"apigw-ws-invoke-{lambda_function_name}"
    source_arn = f"arn:aws:execute-api:{region}:{account_id}:{api_id}/*"
    ensure_lambda_permission(lambda_client, lambda_function_name, statement_id, source_arn)
            
    return f"{api_endpoint}/{stage_name}", api_id



def verify_lambda_deployment(function_name, region, timeout=300):
    """Verify that a Lambda function is properly deployed and ready."""
    import time
    
    logger.info(f"Verifying deployment of {function_name}...")
    lambda_client = boto3.client('lambda', region_name=region)
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Check if function exists and is active
            response = lambda_client.get_function(FunctionName=function_name)
            state = response['Configuration']['State']
            
            if state == 'Active':
                logger.info(f"✅ {function_name} is Active and ready")
                return True
            elif state == 'Pending':
                logger.info(f"⏳ {function_name} is still Pending... waiting")
                time.sleep(5)
                continue
            else:
                logger.warning(f"⚠️  {function_name} is in state: {state}")
                time.sleep(5)
                continue
                
        except Exception as e:
            logger.error(f"❌ Error checking {function_name}: {e}")
            time.sleep(5)
            continue
    
    logger.error(f"❌ Timeout waiting for {function_name} to become ready")
    return False

def verify_api_gateway_deployment(api_name, region, timeout=120):
    """Verify that API Gateway is properly deployed and responding."""
    import time
    import requests
    
    logger.info(f"Verifying API Gateway deployment for {api_name}...")
    
    # Get API Gateway URL
    try:
        apigateway_client = boto3.client('apigateway', region_name=region)
        apis = apigateway_client.get_rest_apis()
        
        target_api = None
        for api in apis['items']:
            if api['name'] == api_name:
                target_api = api
                break
        
        if not target_api:
            logger.error(f"❌ API Gateway {api_name} not found")
            return False
        
        api_url = f"https://{target_api['id']}.execute-api.{region}.amazonaws.com/prod"
        
        # Test API endpoint
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Test with the new /health endpoint
                response = requests.get(f"{api_url}/health", timeout=10)
                if response.status_code == 200:
                    logger.info(f"✅ API Gateway {api_name} is responding at {api_url}/health")
                    return True
                else:
                    logger.info(f"⏳ API Gateway still initializing... got {response.status_code} from /health")
                    time.sleep(10)
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.info(f"⏳ API Gateway not ready yet: {e}")
                time.sleep(10)
                continue
        
        logger.error(f"❌ Timeout waiting for API Gateway {api_name} to respond")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error verifying API Gateway: {e}")
        return False

def wait_for_all_deployments(region):
    """Wait for all deployments to complete and verify they're working."""
    logger.info("\n=== DEPLOYMENT VERIFICATION ===")

    # Use actual deployed function names (with environment suffixes applied)
    # Note: Config Lambda merged into Interface Lambda - no separate verification needed
    deployments_to_verify = [
        (LAMBDA_CONFIG["FunctionName"], "Interface Lambda"),
        # Config Lambda merged into Interface Lambda - skip verification
        ("perplexity-validator-ws-handler", "WebSocket Lambda")  # WebSocket is shared across all environments
    ]
    
    all_success = True
    
    # Verify Lambda functions
    for function_name, description in deployments_to_verify:
        logger.info(f"\n--- Verifying {description} ---")
        if not verify_lambda_deployment(function_name, region):
            logger.error(f"❌ {description} deployment failed")
            all_success = False
        else:
            logger.info(f"✅ {description} deployment successful")
    
    # Verify API Gateway
    logger.info(f"\n--- Verifying API Gateway ---")
    if not verify_api_gateway_deployment(API_GATEWAY_CONFIG["ApiName"], region):
        logger.error("❌ API Gateway deployment failed")
        all_success = False
    else:
        logger.info("✅ API Gateway deployment successful")
    
    if all_success:
        logger.info("\n🎉 ALL DEPLOYMENTS VERIFIED SUCCESSFULLY!")
        return True
    else:
        logger.error("\n💥 SOME DEPLOYMENTS FAILED VERIFICATION")
        return False

async def test_websocket_connection_async(ws_url):
    """Test WebSocket connection asynchronously"""
    try:
        logger.info(f"Testing WebSocket connection to {ws_url}")
        
        async with websockets.connect(ws_url) as websocket:
            logger.info("✅ WebSocket connection established")
            
            # Test subscribe message
            test_message = {
                "action": "subscribe",
                "sessionId": "test_session_" + str(int(time.time()))
            }
            
            await websocket.send(json.dumps(test_message))
            logger.info("✅ Subscribe message sent")
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"✅ Received response: {response}")
                return True
            except asyncio.TimeoutError:
                logger.warning("⚠️ No response received within timeout")
                return True  # Connection worked, just no response
                
    except Exception as e:
        logger.error(f"❌ WebSocket connection test failed: {str(e)}")
        return False

def test_websocket_connection(ws_url):
    """Test WebSocket connection with proper error handling"""
    if not WEBSOCKETS_AVAILABLE:
        logger.warning("⚠️ websockets library not available - skipping WebSocket test")
        logger.info("Install with: pip install websockets")
        return True  # Don't fail deployment for missing optional dependency
    
    try:
        # Run the async test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(test_websocket_connection_async(ws_url))
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"❌ WebSocket test failed: {str(e)}")
        return False

def setup_unified_s3_bucket():
    """Set up unified S3 bucket and separate downloads bucket for hyperplexity storage"""
    try:
        from create_unified_s3_bucket import create_unified_s3_bucket, create_downloads_bucket, test_bucket_structure
        
        # Get environment-specific bucket names from Lambda config
        unified_bucket_name = LAMBDA_CONFIG["Environment"]["Variables"]["S3_UNIFIED_BUCKET"]
        downloads_bucket_name = LAMBDA_CONFIG["Environment"]["Variables"]["S3_DOWNLOAD_BUCKET"]
        
        logger.info(f"🗄️ Setting up S3 buckets for environment...")
        logger.info(f"   Unified bucket: {unified_bucket_name}")
        logger.info(f"   Downloads bucket: {downloads_bucket_name}")
        
        # Create downloads bucket first
        downloads_bucket = create_downloads_bucket(downloads_bucket_name)
        if downloads_bucket:
            logger.info("✅ Downloads bucket created successfully")
        else:
            logger.warning("⚠️ Downloads bucket creation failed")
        
        # Create unified bucket
        unified_bucket = create_unified_s3_bucket(unified_bucket_name)
        if unified_bucket:
            logger.info("✅ Unified S3 bucket created successfully")
            
            # Test bucket structure
            if test_bucket_structure(unified_bucket_name):
                logger.info("✅ Bucket structure verified")
                
                # Note: Downloads bucket created for config lambda use only
                if downloads_bucket:
                    logger.info(f"✅ Downloads bucket available for config lambda: {downloads_bucket}")
                
                return True
            else:
                logger.warning("⚠️ Bucket created but structure test failed")
                return True  # Still proceed
        else:
            logger.error("❌ Failed to create unified S3 bucket")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error setting up S3 buckets: {e}")
        return False

def set_log_retention_policy(function_name, region, retention_days=3):
    """Sets the CloudWatch log retention policy for the given Lambda function."""
    logger.info(f"Setting log retention for {function_name} to {retention_days} days...")
    log_group_name = f"/aws/lambda/{function_name}"
    logs_client = boto3.client('logs', region_name=region)

    try:
        # It can take a moment for the log group to be created after the function is.
        # We will wait and retry a few times.
        retries = 5
        wait_time = 5
        for i in range(retries):
            log_groups_response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
            if 'logGroups' in log_groups_response and any(lg['logGroupName'] == log_group_name for lg in log_groups_response['logGroups']):
                logger.info(f"Log group '{log_group_name}' found.")
                logs_client.put_retention_policy(
                    logGroupName=log_group_name,
                    retentionInDays=retention_days
                )
                logger.info(f"Successfully set retention policy for '{log_group_name}' to {retention_days} days.")
                return
            else:
                logger.info(f"Log group '{log_group_name}' not found. Waiting {wait_time} seconds... (Attempt {i+1}/{retries})")
                time.sleep(wait_time)

        logger.warning(f"Could not find log group '{log_group_name}' after multiple attempts. Please set retention manually.")

    except Exception as e:
        logger.warning(f"Could not set retention policy for {log_group_name}: {e}")

def get_lambda_config_for_mode(mode, base_config):
    """Get Lambda configuration based on deployment mode."""
    config = base_config.copy()

    if mode == 'lightweight':
        config['FunctionName'] = config['FunctionName']  # Keep same name or could be different
        config['MemorySize'] = 128  # Absolute minimum - lazy imports + /health before imports makes this viable
        config['Timeout'] = 30  # Short timeout for API responses
        config['Description'] = 'Lightweight API routing and quick operations'
        config['Environment'] = config.get('Environment', {}).copy()
        config['Environment']['Variables'] = config['Environment'].get('Variables', {}).copy()
        config['Environment']['Variables']['IS_LIGHTWEIGHT_INTERFACE'] = 'true'
        config['Environment']['Variables']['IS_BACKGROUND_PROCESSOR'] = 'false'
        return config

    elif mode == 'background':
        # Change function name for background processor
        base_name = config['FunctionName']
        # Replace 'interface' with 'background' in the function name
        if 'interface' in base_name:
            config['FunctionName'] = base_name.replace('interface', 'background')
        else:
            config['FunctionName'] = base_name + '-background'

        config['MemorySize'] = 512  # Optimized for background processing
        config['Timeout'] = 900  # 15 minutes for complex operations
        config['Description'] = 'Heavy background processing (SQS, AI operations, reports)'
        config['Environment'] = config.get('Environment', {}).copy()
        config['Environment']['Variables'] = config['Environment'].get('Variables', {}).copy()
        config['Environment']['Variables']['IS_LIGHTWEIGHT_INTERFACE'] = 'false'
        config['Environment']['Variables']['IS_BACKGROUND_PROCESSOR'] = 'true'
        return config

    else:  # unified (legacy)
        config['MemorySize'] = 512  # Standard allocation
        config['Timeout'] = 900
        config['Description'] = 'Unified Lambda (legacy mode - all operations)'
        config['Environment'] = config.get('Environment', {}).copy()
        config['Environment']['Variables'] = config['Environment'].get('Variables', {}).copy()
        config['Environment']['Variables']['IS_LIGHTWEIGHT_INTERFACE'] = 'false'
        config['Environment']['Variables']['IS_BACKGROUND_PROCESSOR'] = 'false'
        return config

def configure_sqs_mappings_for_mode(mode, lambda_client, function_name, region):
    """Configure SQS event sources based on mode."""
    if mode == 'lightweight':
        # REMOVE any existing SQS mappings from lightweight Lambda
        logger.info("[MAPPINGS] Lightweight mode: Removing any existing SQS event source mappings")
        try:
            existing_mappings = lambda_client.list_event_source_mappings(FunctionName=function_name)
            for mapping in existing_mappings.get('EventSourceMappings', []):
                if 'sqs' in mapping['EventSourceArn'].lower():
                    uuid = mapping['UUID']
                    logger.info(f"[MAPPINGS] Removing SQS mapping: {mapping['EventSourceArn'].split(':')[-1]} (UUID: {uuid})")
                    lambda_client.delete_event_source_mapping(UUID=uuid)
            logger.info("[MAPPINGS] Lightweight Lambda: All SQS triggers removed")
        except Exception as e:
            logger.warning(f"[MAPPINGS] Error removing SQS mappings: {e}")
        return

    elif mode == 'background':
        # ALL SQS mappings for background
        logger.info("[MAPPINGS] Background mode: Configuring ALL SQS event source mappings")
        configure_sqs_event_source_mappings(lambda_client, function_name, region)

    else:  # unified
        # Legacy behavior - configure mappings
        logger.info("[MAPPINGS] Unified mode: Configuring SQS event source mappings (legacy)")
        configure_sqs_event_source_mappings(lambda_client, function_name, region)

def main():
    """Main function."""
    global PACKAGE_DIR

    parser = argparse.ArgumentParser(description='Create and deploy AWS Lambda interface package')
    parser.add_argument('--deploy', action='store_true', help='Deploy to AWS Lambda after creating package')
    parser.add_argument('--function-name', help='Lambda function name (default: perplexity-validator-interface)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--no-api-gateway', action='store_true', help='Skip API Gateway setup')
    parser.add_argument('--test-api', action='store_true', help='Test the API endpoint after deployment')
    parser.add_argument('--test-websocket', action='store_true', help='Test the WebSocket connection')
    parser.add_argument('--force-rebuild', action='store_true', help='Force rebuilding the package even if it exists')
    parser.add_argument('--no-rebuild', action='store_true', help='Skip rebuilding the package')
    parser.add_argument('--quick-update', action='store_true', help='Quick update: copy only source files, skip dependency downloads')
    parser.add_argument('--setup-db', action='store_true', help='Set up DynamoDB tables for email validation and user tracking')
    parser.add_argument('--skip-db-setup', action='store_true', help='Skip DynamoDB table setup during deployment')
    parser.add_argument('--setup-s3', action='store_true', help='Set up unified S3 bucket')
    parser.add_argument('--skip-s3-setup', action='store_true', help='Skip S3 bucket setup during deployment')
    parser.add_argument('--skip-ws-test', action='store_true', help='Skip WebSocket connection testing during deployment')
    parser.add_argument('--environment', '-e', default='prod', choices=['dev', 'test', 'staging', 'prod'], help='Deployment environment (default: prod)')
    parser.add_argument('--mode', choices=['lightweight', 'background', 'unified'],
                       default='unified',
                       help='Lambda deployment mode: lightweight (API only), background (SQS + heavy ops), unified (legacy - all ops)')
    args = parser.parse_args()
    
    # Apply environment configuration
    print_environment_info(args.environment)
    global LAMBDA_CONFIG, WEBSOCKET_LAMBDA_CONFIG, API_GATEWAY_CONFIG
    LAMBDA_CONFIG = apply_environment_to_lambda_config(LAMBDA_CONFIG, args.environment)
    WEBSOCKET_LAMBDA_CONFIG = apply_environment_to_lambda_config(WEBSOCKET_LAMBDA_CONFIG, args.environment)
    API_GATEWAY_CONFIG = apply_environment_to_api_gateway_config(API_GATEWAY_CONFIG, args.environment)

    # Apply mode-based configuration
    logger.info(f"[DEPLOYMENT MODE] Applying '{args.mode}' mode configuration...")
    LAMBDA_CONFIG = get_lambda_config_for_mode(args.mode, LAMBDA_CONFIG)
    logger.info(f"[DEPLOYMENT MODE] Function Name: {LAMBDA_CONFIG['FunctionName']}")
    logger.info(f"[DEPLOYMENT MODE] Memory: {LAMBDA_CONFIG['MemorySize']} MB")
    logger.info(f"[DEPLOYMENT MODE] Timeout: {LAMBDA_CONFIG['Timeout']} seconds")
    logger.info(f"[DEPLOYMENT MODE] Description: {LAMBDA_CONFIG.get('Description', 'N/A')}")
    logger.info(f"[DEPLOYMENT MODE] IS_LIGHTWEIGHT_INTERFACE: {LAMBDA_CONFIG['Environment']['Variables'].get('IS_LIGHTWEIGHT_INTERFACE', 'N/A')}")
    logger.info(f"[DEPLOYMENT MODE] IS_BACKGROUND_PROCESSOR: {LAMBDA_CONFIG['Environment']['Variables'].get('IS_BACKGROUND_PROCESSOR', 'N/A')}")

    # Get environment-specific stage name
    env_config = load_environment_config(args.environment)
    stage_name = env_config["api_gateway_stage"]

    # Get Lambda function name
    function_name = args.function_name or LAMBDA_CONFIG["FunctionName"]
    
    # Check if we need to build the package
    package_exists = OUTPUT_ZIP.exists()
    
    if args.quick_update:
        if not PACKAGE_DIR.exists():
            logger.error("Package directory doesn't exist. Run full build first before using --quick-update")
            sys.exit(1)
        build_package = False
        quick_update = True
    elif package_exists and not args.force_rebuild:
        if args.no_rebuild:
            build_package = False
            quick_update = False
        else:
            build_package = not input("Package already exists. Skip rebuilding? (y/N): ").lower().startswith('y')
            quick_update = False
    else:
        build_package = True
        quick_update = False
    
    if quick_update:
        logger.info("Quick update: copying only source files...")
        try:
            # Copy source files only (no dependency installation)
            copy_source_files()
            
            # Create the zip package
            create_zip()
            
            # Get ZIP file size
            size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Quick update completed! Package size: {size_mb:.2f} MB")
            logger.info(f"Quick update package created at: {OUTPUT_ZIP}")
        except Exception as e:
            logger.error(f"❌ Quick update failed: {e}")
            sys.exit(1)
    elif build_package:
        logger.info("Creating interface Lambda deployment package...")
        
        try:
            # Create package directory
            PACKAGE_DIR.parent.mkdir(parents=True, exist_ok=True)
            
            # Clean and create package directory
            package_dir = clean_directory(PACKAGE_DIR)
            PACKAGE_DIR = package_dir
            
            logger.info(f"Using package directory: {PACKAGE_DIR}")

            # Install dependencies based on mode
            install_dependencies(args.mode)

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
    
    # Set up DynamoDB tables if requested or if deploying
    if args.setup_db or (args.deploy and not args.skip_db_setup):
        logger.info("Setting up DynamoDB tables...")
        # This function was already updated to call create_validation_runs_table
        db_success = setup_dynamodb_tables(args.region)
        if not db_success:
            logger.error("Failed to set up DynamoDB tables")
            if args.deploy:
                logger.warning("Continuing with deployment despite DB setup failure...")
    
    # Set up unified S3 bucket if requested
    if args.setup_s3 or (args.deploy and not args.skip_s3_setup):
        s3_success = setup_unified_s3_bucket()
        if not s3_success:
            logger.error("Failed to set up unified S3 bucket")
            if args.deploy:
                logger.warning("Continuing with deployment despite S3 setup failure...")
    
    # Set up SQS queues if deploying
    if args.deploy:
        logger.info("Setting up SQS queues...")
        sqs_success = setup_sqs_queues(args.region)
        if not sqs_success:
            logger.error("Failed to set up SQS queues")
            logger.warning("Continuing with deployment despite SQS setup failure...")
    
    # Deploy if requested
    if args.deploy:
        try:
            deploy_api_gateway = not args.no_api_gateway
            success, api_url = deploy_to_lambda(
                args.function_name,
                args.region,
                deploy_api_gateway,
                stage_name,
                args.mode
            )
            
            if not success:
                return 1
            
            # After successful deployment, set up the SQS triggers
            lambda_client = boto3.client('lambda', region_name=args.region)
            setup_sqs_triggers(lambda_client, function_name, args.region)

            if api_url and args.test_api:
                logger.info("Testing API endpoint...")
                test_api_endpoint(api_url)
            
            # Deploy WebSocket handler
            logger.info("\n--- Deploying WebSocket Infrastructure ---")
            ws_package_zip = SCRIPT_DIR / "websocket_lambda_package.zip"
            create_websocket_lambda_package(ws_package_zip)
            deploy_websocket_lambda(ws_package_zip, args.region)
            # Use shared WebSocket infrastructure (always prod stage) regardless of environment
            ws_api_url, ws_api_id = setup_websocket_api("perplexity-validator-ws-handler", args.region, "prod")
            
            if ws_api_url:
                logger.info(f"WebSocket API deployed successfully. Endpoint: {ws_api_url}")
                
                # Get account ID for IAM policy
                account_id = boto3.client('sts').get_caller_identity()['Account']

                # Grant the main interface lambda permission to post to the WebSocket
                main_lambda_role_name = LAMBDA_CONFIG['Role'].split('/')[-1]
                iam_client = boto3.client('iam')
                policy_name = "WebSocketAPIPostMessagePolicy"
                policy_document = {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": "execute-api:ManageConnections",
                        "Resource": f"arn:aws:execute-api:{args.region}:{account_id}:{ws_api_id}/*"
                    }]
                }
                try:
                    iam_client.put_role_policy(
                        RoleName=main_lambda_role_name,
                        PolicyName=policy_name,
                        PolicyDocument=json.dumps(policy_document)
                    )
                    logger.info(f"Attached WebSocket post policy to role {main_lambda_role_name}.")
                except Exception as e:
                     logger.warning(f"Could not attach WebSocket policy to role {main_lambda_role_name}: {e}")

                # Update the main interface lambda's environment (preserve environment-configured WebSocket URL)
                lambda_client = boto3.client('lambda', region_name=args.region)
                try:
                    # Use the WebSocket URL from environment configuration, not the deployment-generated one
                    configured_ws_url = LAMBDA_CONFIG['Environment']['Variables'].get('WEBSOCKET_API_URL', ws_api_url)
                    logger.info(f"Updating interface lambda {function_name} with WebSocket API URL: {configured_ws_url}")
                    lambda_client.update_function_configuration(
                        FunctionName=function_name,
                        Environment={
                            'Variables': {
                                **LAMBDA_CONFIG['Environment']['Variables'],
                                'WEBSOCKET_API_URL': configured_ws_url
                            }
                        }
                    )
                    logger.info("Successfully updated interface lambda with WebSocket API URL.")
                    
                    # Verify the environment variable was set
                    time.sleep(2)  # Wait for update to propagate
                    function_config = lambda_client.get_function(FunctionName=function_name)
                    env_vars = function_config['Configuration']['Environment']['Variables']
                    if 'WEBSOCKET_API_URL' in env_vars:
                        logger.info(f"Verified: WEBSOCKET_API_URL = {env_vars['WEBSOCKET_API_URL']}")
                    else:
                        logger.warning("WEBSOCKET_API_URL was not found in environment variables after update")
                        
                except Exception as e:
                    logger.error(f"Failed to update interface lambda environment: {e}")
                    raise
                
                # Frontend WebSocket URL is manually configured for shared infrastructure
                # (commented out to preserve environment-specific configuration)
                # try:
                #     html_path = PROJECT_DIR / "frontend" / "perplexity_validator_interface2.html"
                #     with open(html_path, 'r', encoding='utf-8') as f:
                #         html_content = f.read()
                #     
                #     # Replace the placeholder
                #     new_html_content = html_content.replace(
                #         'wss://<REPLACE_WITH_YOUR_WEBSOCKET_ID>.execute-api.us-east-1.amazonaws.com/prod',
                #         ws_api_url
                #     )
                #     
                #     with open(html_path, 'w', encoding='utf-8') as f:
                #         f.write(new_html_content)
                #     logger.info(f"Updated WebSocket URL in {html_path}")
                # except Exception as e:
                #     logger.error(f"Failed to inject WebSocket URL into HTML file: {e}")
                logger.info(f"Preserving manually configured frontend WebSocket URLs for shared infrastructure")
            else:
                logger.error("Failed to deploy WebSocket API")
        except Exception as e:
            logger.error(f"Error deploying WebSocket infrastructure: {str(e)}")


        # --- Test WebSocket Connection ---
        if not args.skip_ws_test:
            logger.info("\n=== TESTING WEBSOCKET CONNECTION ===")
            if ws_api_url:
                if test_websocket_connection(ws_api_url):
                    logger.info("✅ WebSocket connection test passed!")
                else:
                    logger.warning("⚠️ WebSocket connection test failed - but continuing deployment")
        else:
            logger.info("\n=== SKIPPING WEBSOCKET CONNECTION TEST (--skip-ws-test) ===")
        
        # --- Verify All Deployments ---
        logger.info("\n=== VERIFYING ALL DEPLOYMENTS ===")
        if not wait_for_all_deployments(args.region):
            logger.error("❌ Deployment verification failed!")
            return 1
        

    else:
        logger.info("\nTo deploy to AWS Lambda with API Gateway, use:")
        logger.info(f"python {__file__} --deploy [--test-api]")
        
        # Test existing WebSocket setup if requested
        if args.test_websocket:
            logger.info("\n=== TESTING EXISTING WEBSOCKET SETUP ===")
            try:
                # Get current WebSocket URL from Lambda env
                lambda_client = boto3.client('lambda')
                function_config = lambda_client.get_function_configuration(FunctionName=LAMBDA_CONFIG["FunctionName"])
                ws_url = function_config.get('Environment', {}).get('Variables', {}).get('WEBSOCKET_API_URL')
                
                if ws_url:
                    logger.info(f"Found WebSocket URL: {ws_url}")
                    if test_websocket_connection(ws_url):
                        logger.info("✅ WebSocket connection test passed!")
                    else:
                        logger.warning("⚠️ WebSocket connection test failed!")
                else:
                    logger.warning("⚠️ No WEBSOCKET_API_URL found in Lambda environment")
                    
            except Exception as e:
                logger.warning(f"Could not test WebSocket: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main()) 