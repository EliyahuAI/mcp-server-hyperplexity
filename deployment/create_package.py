#!/usr/bin/env python
"""
Script to create and deploy a minimal AWS Lambda deployment package.
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

# Add project root to sys.path to allow for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import environment configuration helper
from environment_config import apply_environment_to_lambda_config, print_environment_info

# Directory setup
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
LAMBDA_SRC_DIR = SRC_DIR / "lambdas" / "validation"
SHARED_SRC_DIR = SRC_DIR / "shared"
PACKAGE_DIR = SCRIPT_DIR / "package"
OUTPUT_ZIP = SCRIPT_DIR / "lambda_package.zip"

# Lambda configuration
LAMBDA_CONFIG = {
    "FunctionName": "perplexity-validator",
    "Runtime": "python3.9",
    "Handler": "lambda_function.lambda_handler", # This will be created in the package root
    "Timeout": 870,  # 14.5 minutes in seconds (14m 30s)
    "MemorySize": 512,  # Optimized: was 1024MB, max used 334MB
    "Role": "arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7",
    "Environment": {
        "Variables": {
            "S3_UNIFIED_BUCKET": "hyperplexity-storage",  # Unified bucket for all storage
            "S3_DOWNLOAD_BUCKET": "hyperplexity-storage", # Same bucket but hyperplexity/downloads/ has public access
            # Legacy variables for compatibility during transition
            "S3_CACHE_BUCKET": "hyperplexity-storage",
            "S3_RESULTS_BUCKET": "hyperplexity-storage",
            "S3_CONFIG_BUCKET": "hyperplexity-storage",
            "WEBSOCKET_API_URL": "wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod",
            # Smart Delegation System SQS Queues
            "ASYNC_VALIDATOR_QUEUE": "https://sqs.us-east-1.amazonaws.com/400232868802/perplexity-validator-async-queue",
            "INTERFACE_COMPLETION_QUEUE": "https://sqs.us-east-1.amazonaws.com/400232868802/perplexity-validator-completion-queue",
            "MAX_SYNC_INVOCATION_TIME": "5.0",
            "VALIDATOR_SAFETY_BUFFER": "3.0"
        }
    },
    "TracingConfig": {
        "Mode": "Active"  # Enable X-Ray tracing for better debugging
    }
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
                PACKAGE_DIR = dir_path.parent / f"package_{timestamp}"
                dir_path = PACKAGE_DIR
    
    dir_path.parent.mkdir(parents=True, exist_ok=True)
    dir_path.mkdir(exist_ok=True)
    return dir_path

def install_dependencies():
    """Install dependencies to package directory."""
    logger.info(f"Installing dependencies from {SCRIPT_DIR / 'requirements-lambda.txt'}...")
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "-r", str(SCRIPT_DIR / "requirements-lambda.txt"),
                "-t", str(PACKAGE_DIR),
                "--no-cache-dir",
                "--platform", "manylinux2014_x86_64",
                "--only-binary=:all:"
            ])
            logger.info("Dependencies installed successfully.")
            break
        except subprocess.CalledProcessError as e:
            logger.error(f"Error installing dependencies (attempt {attempt}/{max_attempts}): {e}")
            if attempt == max_attempts:
                raise
            logger.info("Retrying in 2 seconds...")
            time.sleep(2)

def verify_dependencies():
    """Verify that all critical dependencies are properly installed."""
    logger.info("Verifying critical dependencies...")
    
    # Map of package names to their import names
    critical_deps = {
        "aiohttp": "aiohttp",
        "typing_extensions": "typing_extensions",
        "python-dateutil": "dateutil",  # Changed from python_dateutil
        "async_timeout": "async_timeout",
        "attrs": "attrs",
        "multidict": "multidict",
        "yarl": "yarl",
        "frozenlist": "frozenlist",
        "idna": "idna"
    }
    
    verify_file = PACKAGE_DIR / "verify_deps.py"
    with open(verify_file, "w") as f:
        f.write("# Dependency verification\n")
        for pkg_name, import_name in critical_deps.items():
            f.write(f"import {import_name}\n")
            f.write(f"print(f'Successfully imported {pkg_name}')\n")
    
    try:
        logger.info("Testing imports in the package directory...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE_DIR)
        
        result = subprocess.run(
            [sys.executable, str(verify_file)],
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("All critical dependencies verified successfully.")
            for line in result.stdout.splitlines():
                logger.info(f"  {line}")
        else:
            logger.warning("Some dependencies failed verification!")
            logger.error(f"Error output: {result.stderr}")
            logger.info("Installing missing dependencies directly...")
            
            for pkg_name in critical_deps.keys():
                logger.info(f"Ensuring {pkg_name} is installed...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    pkg_name,
                    "-t", str(PACKAGE_DIR),
                    "--no-cache-dir",
                    "--platform", "manylinux2014_x86_64",
                    "--only-binary=:all:"
                ])
    except Exception as e:
        logger.error(f"Error during dependency verification: {str(e)}")
        logger.info("Proceeding with direct installation of critical dependencies...")
        
        for pkg_name in critical_deps.keys():
            logger.info(f"Installing {pkg_name} directly...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                pkg_name,
                "-t", str(PACKAGE_DIR),
                "--no-cache-dir",
                "--platform", "manylinux2014_x86_64",
                "--only-binary=:all:"
            ])
    
    if verify_file.exists():
        verify_file.unlink()

def copy_source_files():
    """Copy necessary source files."""
    logger.info("Copying source files...")
    
    # 1. Copy all files from the new validation lambda source
    shutil.copytree(LAMBDA_SRC_DIR, PACKAGE_DIR, dirs_exist_ok=True)
    logger.info(f"Copied contents of {LAMBDA_SRC_DIR} to {PACKAGE_DIR}")

    # 2. Copy all shared files into the package root
    shutil.copytree(SHARED_SRC_DIR, PACKAGE_DIR, dirs_exist_ok=True)
    logger.info(f"Copied shared modules from {SHARED_SRC_DIR} to {PACKAGE_DIR}")
    
    # 3. Copy prompts.yml for validation lambda (needed by schema_validator_simplified.py)
    prompts_file = PROJECT_DIR / "src" / "prompts.yml"
    if prompts_file.exists():
        shutil.copy(prompts_file, PACKAGE_DIR / "prompts.yml")
        logger.info("Copied prompts.yml for validation lambda")
    else:
        logger.warning(f"prompts.yml not found at {prompts_file}")
    
    # 4. Copy pricing_data.csv for cost calculations
    pricing_file = PROJECT_DIR / "src" / "pricing_data.csv"
    if pricing_file.exists():
        shutil.copy(pricing_file, PACKAGE_DIR / "pricing_data.csv")
        logger.info("Copied pricing_data.csv for cost calculations")
    else:
        logger.warning(f"pricing_data.csv not found at {pricing_file}")
    
    # 5. Copy config directory for enhanced batch manager
    config_src_dir = PROJECT_DIR / "src" / "config"
    if config_src_dir.exists():
        # Copy entire config directory
        config_dest_dir = PACKAGE_DIR / "config"
        if config_dest_dir.exists():
            shutil.rmtree(config_dest_dir)
        shutil.copytree(config_src_dir, config_dest_dir)
        logger.info("Copied config directory for enhanced batch manager")
    else:
        logger.warning(f"config directory not found at {config_src_dir}")
    
    # 6. Copy logo files for PDF receipts
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

def create_zip():
    """Create deployment zip file."""
    logger.info(f"Creating ZIP file: {OUTPUT_ZIP}")
    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(PACKAGE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, PACKAGE_DIR)
                zipf.write(file_path, arcname)

def deploy_to_lambda(function_name=None, region=None, s3_bucket=None, verify=False, run_test=False, timeout=None, test_event=None):
    """Deploy the Lambda package to AWS."""
    if function_name:
        LAMBDA_CONFIG["FunctionName"] = function_name
    
    if s3_bucket:
        LAMBDA_CONFIG["Environment"]["Variables"]["S3_CACHE_BUCKET"] = s3_bucket
        
    if timeout:
        LAMBDA_CONFIG["Timeout"] = timeout
        logger.info(f"Setting Lambda function timeout to {timeout} seconds")

    lambda_client = boto3.client('lambda', region_name=region)
    
    logger.info(f"Deploying to Lambda function: {LAMBDA_CONFIG['FunctionName']}")
    
    try:
        # Check if function exists
        try:
            lambda_client.get_function(FunctionName=LAMBDA_CONFIG["FunctionName"])
            function_exists = True
            logger.info(f"Lambda function {LAMBDA_CONFIG['FunctionName']} exists. Updating...")
        except lambda_client.exceptions.ResourceNotFoundException:
            function_exists = False
            logger.info(f"Lambda function {LAMBDA_CONFIG['FunctionName']} does not exist. Creating new function...")
        
        # Read deployment package
        with open(OUTPUT_ZIP, 'rb') as zip_file:
            zip_content = zip_file.read()
        
        if function_exists:
            # Update function code
            update_code_args = {
                'FunctionName': LAMBDA_CONFIG["FunctionName"],
                'ZipFile': zip_content,
            }
            
            # Retry logic for ResourceConflictException on code update
            max_retries = 5
            retry_delay = 10  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = lambda_client.update_function_code(**update_code_args)
                    logger.info(f"Function code updated successfully. Version: {response.get('Version')}")
                    break
                except lambda_client.exceptions.ResourceConflictException as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Lambda update in progress during code update (attempt {attempt + 1}/{max_retries}). Waiting {retry_delay}s before retry...")
                        time.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                    else:
                        logger.error(f"Failed to update function code after {max_retries} attempts")
                        raise
            
            # Wait for the update to complete
            logger.info("Waiting for code update to complete...")
            for i in range(5):
                time.sleep(3)
                try:
                    function_info = lambda_client.get_function(
                        FunctionName=LAMBDA_CONFIG["FunctionName"]
                    )
                    state = function_info['Configuration']['State']
                    if state == 'Active':
                        logger.info("Function is now in Active state.")
                        break
                    else:
                        logger.info(f"Function state: {state}. Waiting...")
                except Exception as e:
                    logger.error(f"Error checking function state: {str(e)}")
            
            # Update function configuration
            update_config_args = {
                'FunctionName': LAMBDA_CONFIG["FunctionName"],
                'Runtime': LAMBDA_CONFIG["Runtime"],
                'Role': LAMBDA_CONFIG["Role"],
                'Handler': LAMBDA_CONFIG["Handler"],
                'Timeout': LAMBDA_CONFIG["Timeout"],
                'MemorySize': LAMBDA_CONFIG["MemorySize"],
                'Environment': LAMBDA_CONFIG["Environment"],
                'TracingConfig': LAMBDA_CONFIG.get("TracingConfig", {'Mode': 'PassThrough'})
            }
            
            logger.info(f"Updating function configuration with timeout={LAMBDA_CONFIG['Timeout']}s and memory={LAMBDA_CONFIG['MemorySize']}MB")
            
            # Retry logic for ResourceConflictException
            max_retries = 5
            retry_delay = 10  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = lambda_client.update_function_configuration(**update_config_args)
                    logger.info("Function configuration updated successfully.")
                    break
                except lambda_client.exceptions.ResourceConflictException as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Lambda update in progress (attempt {attempt + 1}/{max_retries}). Waiting {retry_delay}s before retry...")
                        time.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                    else:
                        logger.error(f"Failed to update function configuration after {max_retries} attempts")
                        raise
        else:
            # Create new function
            create_function_args = {
                'FunctionName': LAMBDA_CONFIG["FunctionName"],
                'Runtime': LAMBDA_CONFIG["Runtime"],
                'Role': LAMBDA_CONFIG["Role"],
                'Handler': LAMBDA_CONFIG["Handler"],
                'Code': {'ZipFile': zip_content},
                'Timeout': LAMBDA_CONFIG["Timeout"],
                'MemorySize': LAMBDA_CONFIG["MemorySize"],
                'Environment': LAMBDA_CONFIG["Environment"],
                'TracingConfig': LAMBDA_CONFIG.get("TracingConfig", {'Mode': 'PassThrough'})
            }
            
            response = lambda_client.create_function(**create_function_args)
            logger.info(f"New function created successfully. ARN: {response.get('FunctionArn')}")
        
        logger.info("\nDeployment completed successfully!")
        logger.info(f"Lambda function URL: https://console.aws.amazon.com/lambda/home?region={region or 'us-east-1'}#/functions/{LAMBDA_CONFIG['FunctionName']}")
        
        # Run test if requested
        if run_test:
            logger.info("\nRunning test after deployment...")
            test_lambda_function(LAMBDA_CONFIG["FunctionName"], region, test_event)
        
        return True
        
    except Exception as e:
        logger.error(f"Error deploying to Lambda: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_lambda_function(function_name, region=None, test_event=None):
    """Test the Lambda function with the enhanced test event."""
    logger.info(f"Testing Lambda function: {function_name}")
    
    try:
        # Initialize Lambda client with increased timeout
        lambda_client = boto3.client(
            'lambda', 
            region_name=region,
            config=Config(
                connect_timeout=120,
                read_timeout=900,  # Increase read timeout to 15 minutes (must be >= lambda timeout)
                retries={'max_attempts': 0}
            )
        )
        
        # Load test event
        if test_event:
            # If test_event is a path, load it
            try:
                # Normalize path to handle both forward and backslashes
                test_event_path = Path(test_event.replace('\\', '/'))
                logger.info(f"Looking for test event at: {test_event_path}")
                
                if test_event_path.exists():
                    logger.info(f"Loading test event from {test_event_path}")
                    with open(test_event_path, 'r') as f:
                        test_event_data = json.load(f)
                else:
                    # Try alternative path constructions
                    alternative_paths = [
                        PROJECT_DIR / test_event,
                        PROJECT_DIR / "test_events" / test_event,
                        Path(os.path.abspath(test_event))
                    ]
                    
                    for alt_path in alternative_paths:
                        logger.info(f"Trying alternative path: {alt_path}")
                        if alt_path.exists():
                            logger.info(f"Found test event at alternative path: {alt_path}")
                            with open(alt_path, 'r') as f:
                                test_event_data = json.load(f)
                            break
                    else:
                        logger.warning(f"Custom test event file not found at any tried location: {test_event}")
                        logger.info(f"Falling back to default test event")
                        test_event_path = PROJECT_DIR / "test_events" / "enhanced_test_event.json"
                        with open(test_event_path, 'r') as f:
                            test_event_data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading test event: {e}")
                logger.info(f"Falling back to default test event")
                test_event_path = PROJECT_DIR / "test_events" / "enhanced_test_event.json"
                with open(test_event_path, 'r') as f:
                    test_event_data = json.load(f)
        else:
            test_event_path = PROJECT_DIR / "test_events" / "enhanced_test_event.json"
            with open(test_event_path, 'r') as f:
                test_event_data = json.load(f)
        
        logger.info("Invoking Lambda function...")
        
        # First, get the log group name
        logs_client = boto3.client('logs', region_name=region)
        log_group_name = f"/aws/lambda/{function_name}"
        
        # Check if log group exists
        try:
            log_groups = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
            if log_groups.get('logGroups'):
                logger.info(f"CloudWatch Logs group exists: {log_group_name}")
            else:
                logger.warning(f"CloudWatch Logs group does not exist yet: {log_group_name}")
                logger.info("Logs will be created automatically when Lambda function writes to stdout/stderr")
        except Exception as e:
            logger.warning(f"Could not verify log group: {e}")
            logger.info("Will try to create log group automatically when function executes")
        
        # Get the timestamp before invocation to filter logs 
        start_time = int(time.time() * 1000) - 60000  # Start 1 minute before now

        # Invoke Lambda function
        logger.info("Invoking Lambda with 15-minute timeout...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(test_event_data),
            LogType='Tail'  # Request the last 4KB of logs
        )
        
        # Parse base64 encoded logs from the response
        if 'LogResult' in response:
            log_result = base64.b64decode(response['LogResult']).decode()
            logger.info(f"Lambda execution log:\n{log_result}")
        
        # Parse response
        if 'Payload' in response:
            response_payload = json.loads(response['Payload'].read())
            
            # Log the full response for debugging
            logger.info("Full Lambda response:")
            logger.info(json.dumps(response_payload, indent=2))
            
            if response_payload.get('statusCode') == 200:
                results = response_payload['body']
                logger.info("Validation completed successfully!")
                logger.info(f"Cache stats: {results['metadata']}")
                
                # Print validation results
                if results.get('validation_results'):
                    for row_idx, row_results in results['validation_results'].items():
                        logger.info(f"\nRow {row_idx} Results:")
                        for target, result in row_results.items():
                            if target not in ['next_check', 'reasons']:
                                logger.info(f"  {target}:")
                                if 'value' in result:
                                    logger.info(f"    Value: {result['value']}")
                                if 'confidence' in result and 'confidence_level' in result:
                                    logger.info(f"    Confidence: {result['confidence']} ({result['confidence_level']})")
                                if 'sources' in result:
                                    logger.info(f"    Sources: {result['sources']}")
                                if 'quote' in result and result['quote']:
                                    logger.info(f"    Quote: {result['quote']}")
                        
                        logger.info(f"  Next Check: {row_results.get('next_check', 'None')}")
                        logger.info(f"  Reasons: {row_results.get('reasons', [])}")
                else:
                    logger.info("No validation results returned, likely using cached results")
                
                # Print raw API responses if available
                if results.get('raw_responses'):
                    logger.info("\n=== RAW PERPLEXITY API RESPONSES ===")
                    for response_id, response_data in results['raw_responses'].items():
                        logger.info(f"\nResponse ID: {response_id}")
                        logger.info(f"Fields: {response_data.get('fields', [])}")
                        logger.info(f"Is Cached: {response_data.get('is_cached', False)}")
                        
                        # Log the prompt
                        logger.info("\nPrompt:")
                        prompt_lines = response_data.get('prompt', '').split('\n')
                        for line in prompt_lines[:20]:  # Show first 20 lines
                            logger.info(f"  {line}")
                        if len(prompt_lines) > 20:
                            logger.info(f"  ... ({len(prompt_lines) - 20} more lines)")
                        
                        # Log the API response content
                        if 'response' in response_data:
                            api_response = response_data['response']
                            
                            # Show citations
                            if 'citations' in api_response and api_response['citations']:
                                logger.info("\nCitations:")
                                for i, citation in enumerate(api_response['citations']):
                                    logger.info(f"  [{i+1}] {citation}")
                            
                            # Extract and format the content field
                            if 'choices' in api_response and api_response['choices']:
                                content = api_response['choices'][0].get('message', {}).get('content', '')
                                if content:
                                    logger.info("\nModel Response Content:")
                                    try:
                                        # Try to pretty-print the content as JSON
                                        content_json = json.loads(content)
                                        logger.info(json.dumps(content_json, indent=2))
                                    except:
                                        # If not JSON, print as is
                                        logger.info(content)
                    
                    logger.info("=== END RAW RESPONSES ===\n")
                
                return True
            else:
                error_msg = response_payload.get('body', {}).get('error')
                if not error_msg:
                    error_msg = response_payload.get('errorMessage', 'Unknown error')
                logger.error(f"Error in Lambda execution: {error_msg}")
                
                # Log function error if available
                if 'FunctionError' in response:
                    logger.error(f"Function error type: {response['FunctionError']}")
                
                # Log any stack trace if available
                if 'errorMessage' in response_payload:
                    logger.error("Error message:")
                    logger.error(response_payload['errorMessage'])
                if 'stackTrace' in response_payload:
                    logger.error("Stack trace:")
                    for line in response_payload['stackTrace']:
                        logger.error(line)
        else:
            logger.error("No payload returned from Lambda function")
        
        # Fetch CloudWatch logs
        end_time = int(time.time() * 1000)
        logger.info(f"Fetching CloudWatch logs from {log_group_name}...")
        
        try:
            # Wait a moment for logs to be available
            time.sleep(3)
            
            # Get log streams, sorted by last event time
            log_streams = logs_client.describe_log_streams(
                logGroupName=log_group_name,
                orderBy='LastEventTime',
                descending=True,
                limit=3
            )
            
            if 'logStreams' in log_streams and log_streams['logStreams']:
                latest_stream = log_streams['logStreams'][0]['logStreamName']
                logger.info(f"Latest log stream: {latest_stream}")
                
                # Get log events
                log_events = logs_client.get_log_events(
                    logGroupName=log_group_name,
                    logStreamName=latest_stream,
                    startTime=start_time,
                    endTime=end_time,
                    limit=1000
                )
                
                if 'events' in log_events and log_events['events']:
                    logger.info("=== CLOUDWATCH LOGS ===")
                    for event in log_events['events']:
                        logger.info(event['message'])
                    logger.info("=== END LOGS ===")
                else:
                    logger.warning("No log events found in the specified time range")
            else:
                logger.warning("No log streams found for this function")
        except Exception as e:
            logger.error(f"Error retrieving CloudWatch logs: {e}")
                
        return False
        
    except Exception as e:
        logger.error(f"Error testing Lambda: {e}")
        logger.error("Full traceback:")
        import traceback
        logger.error(traceback.format_exc())
        return False

def get_cloudwatch_logs(function_name, region=None, minutes=10):
    """Utility function to fetch the latest CloudWatch logs for a Lambda function."""
    try:
        import traceback
        logs_client = boto3.client('logs', region_name=region)
        log_group_name = f"/aws/lambda/{function_name}"
        
        # Calculate start time (minutes ago)
        start_time = int((time.time() - (minutes * 60)) * 1000)
        end_time = int(time.time() * 1000)
        
        logger.info(f"Fetching CloudWatch logs for {function_name} from the last {minutes} minutes...")
        
        # Get the most recent log streams
        log_streams = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy='LastEventTime',
            descending=True,
            limit=3
        )
        
        if not log_streams.get('logStreams'):
            logger.warning(f"No log streams found for {log_group_name}")
            return False
            
        # Get logs from the most recent stream
        latest_stream = log_streams['logStreams'][0]['logStreamName']
        logger.info(f"Reading logs from stream: {latest_stream}")
        
        log_events = logs_client.get_log_events(
            logGroupName=log_group_name,
            logStreamName=latest_stream,
            startTime=start_time,
            endTime=end_time,
            limit=1000  # Increase if needed
        )
        
        if not log_events.get('events'):
            logger.warning("No log events found in the specified time range")
            return False
            
        # Print the logs
        logger.info("\n=== CLOUDWATCH LOGS ===")
        for event in log_events['events']:
            logger.info(event['message'])
        logger.info("=== END LOGS ===\n")
        
        return True
        
    except Exception as e:
        logger.error(f"Error retrieving CloudWatch logs: {e}")
        logger.error(traceback.format_exc())
        return False

def delete_s3_cache(bucket_name, region=None):
    """Delete all validation cache objects from the S3 bucket."""
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=region)
        
        # Define cache prefixes for both unified and legacy structures
        cache_prefixes = [
            'cache/perplexity/',      # New unified structure
            'cache/claude/',          # New unified structure  
            'validation_cache/',      # Legacy structure
            'claude_cache/'           # Legacy structure
        ]
        
        total_objects = 0
        deleted_objects = 0
        
        for prefix in cache_prefixes:
            logger.info(f"Listing objects in s3://{bucket_name}/{prefix}")
            
            # List objects with this prefix
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
            
            prefix_objects = 0
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                    
                objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]
                prefix_objects += len(objects_to_delete)
                
                if not objects_to_delete:
                    continue
                    
                # Delete objects in batches of 1000 (S3 limit)
                batch_size = 1000
                for i in range(0, len(objects_to_delete), batch_size):
                    batch = objects_to_delete[i:i + batch_size]
                    response = s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': batch, 'Quiet': False}
                    )
                    
                    if 'Deleted' in response:
                        deleted_objects += len(response['Deleted'])
                        
                    if 'Errors' in response and response['Errors']:
                        for error in response['Errors']:
                            logger.error(f"Error deleting {error['Key']}: {error['Code']} - {error['Message']}")
            
            total_objects += prefix_objects
            if prefix_objects > 0:
                logger.info(f"Found {prefix_objects} objects in {prefix}")
        
        if total_objects == 0:
            logger.info("No cache objects found to delete.")
        else:
            logger.info(f"Successfully deleted {deleted_objects}/{total_objects} cache objects from s3://{bucket_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting cache: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Main function."""
    global PACKAGE_DIR  # Move global declaration to the start of the function
    
    parser = argparse.ArgumentParser(description='Create and deploy AWS Lambda package')
    parser.add_argument('--deploy', action='store_true', help='Deploy to AWS Lambda after creating package')
    parser.add_argument('--function-name', help='Lambda function name (default: perplexity-validator)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--s3-bucket', default='hyperplexity-storage', help='S3 bucket for caching (default: hyperplexity-storage)')
    parser.add_argument('--verify', action='store_true', help='Verify the Lambda function after deployment')
    parser.add_argument('--force-rebuild', action='store_true', help='Force rebuilding the package even if it exists')
    parser.add_argument('--no-rebuild', action='store_true', help='Skip rebuilding the package if it exists')
    parser.add_argument('--run-test', action='store_true', help='Run a test of the function after deployment')
    parser.add_argument('--test-only', action='store_true', help='Only run a test without deploying')
    parser.add_argument('--delete-cache', action='store_true', help='Delete all validation cache objects from the S3 bucket')
    parser.add_argument('--test-event', help='Path to a custom test event JSON file to use for testing')
    parser.add_argument('--logs', action='store_true', help='Fetch the latest CloudWatch logs for the Lambda function')
    parser.add_argument('--logs-minutes', type=int, default=30, help='Number of minutes of logs to fetch (default: 30)')
    parser.add_argument('--timeout', type=int, default=870, help='Lambda execution timeout in seconds (default: 870 = 14.5 minutes)')
    parser.add_argument('--diagnose-logs', action='store_true', help='Deploy and test a function to diagnose CloudWatch Logs permissions')
    parser.add_argument('--environment', '-e', default='prod', choices=['dev', 'test', 'staging', 'prod'], help='Deployment environment (default: prod)')
    args = parser.parse_args()
    
    # Apply environment configuration
    print_environment_info(args.environment)
    global LAMBDA_CONFIG
    LAMBDA_CONFIG = apply_environment_to_lambda_config(LAMBDA_CONFIG, args.environment)
    
    # Special handling for diagnose logs
    if args.diagnose_logs:
        function_name = "perplexity-validator-logs-test"
        logger.info(f"Setting up log diagnostics function: {function_name}")
        
        # Build the package
        logger.info("Creating diagnostic package...")
        package_dir = clean_directory(PACKAGE_DIR)
        PACKAGE_DIR = package_dir
        
        # Install required dependencies
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "boto3",
            "-t", str(PACKAGE_DIR),
            "--no-cache-dir",
            "--platform", "manylinux2014_x86_64",
            "--only-binary=:all:"
        ])
        
        # Copy diagnose_logs.py as lambda_function.py
        diagnose_logs = SRC_DIR / "diagnose_logs.py"
        if diagnose_logs.exists():
            shutil.copy(diagnose_logs, PACKAGE_DIR / "lambda_function.py")
            logger.info("Copied diagnose_logs.py as lambda_function.py")
        else:
            logger.error("diagnose_logs.py not found. Cannot continue.")
            return 1
            
        # Create ZIP file
        create_zip()
        
        # Deploy
        test_lambda_config = {
            "FunctionName": function_name,
            "Runtime": "python3.9",
            "Handler": "lambda_function.lambda_handler",
            "Timeout": 30,
            "MemorySize": 512,
            "Role": LAMBDA_CONFIG["Role"],
            "Environment": {"Variables": {}},
            "TracingConfig": {"Mode": "Active"}
        }
        
        # Store original config
        original_config = LAMBDA_CONFIG.copy()
        
        # Use test config
        LAMBDA_CONFIG.update(test_lambda_config)
        
        # Deploy
        success = deploy_to_lambda()
        
        if success:
            # Wait for the function to be active
            logger.info("Waiting for function to reach Active state...")
            max_wait_time = 30  # seconds
            wait_interval = 3   # seconds
            
            for i in range(int(max_wait_time / wait_interval)):
                try:
                    function_info = lambda_client.get_function(
                        FunctionName=function_name
                    )
                    state = function_info['Configuration']['State']
                    logger.info(f"Function state: {state}")
                    
                    if state == 'Active':
                        logger.info("Function is now active!")
                        break
                    else:
                        logger.info(f"Function is in {state} state, waiting...")
                        time.sleep(wait_interval)
                except Exception as e:
                    logger.error(f"Error checking function state: {e}")
                    time.sleep(wait_interval)
            
            # Test the function
            logger.info("Invoking logs diagnostics function...")
            lambda_client = boto3.client('lambda', region_name=args.region)
            response = lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                LogType='Tail'
            )
            
            # Display logs
            if 'LogResult' in response:
                log_result = base64.b64decode(response['LogResult']).decode()
                logger.info(f"Log diagnostic output:\n{log_result}")
            
            # Wait for logs to propagate
            logger.info("Waiting 5 seconds for logs to propagate...")
            time.sleep(5)
            
            # Try to fetch CloudWatch logs
            get_cloudwatch_logs(function_name, args.region, 5)
        
        # Restore original config
        LAMBDA_CONFIG.update(original_config)
        return 0
    
    # Get Lambda function name
    function_name = args.function_name or LAMBDA_CONFIG["FunctionName"]
    
    # Just fetch logs if that's all that's requested
    if args.logs and not (args.deploy or args.test_only or args.delete_cache or args.force_rebuild or args.no_rebuild):
        logger.info(f"Fetching CloudWatch logs for {function_name}...")
        get_cloudwatch_logs(function_name, args.region, args.logs_minutes)
        return 0
    
    # Handle delete-cache option
    if args.delete_cache:
        logger.info(f"Deleting validation cache from S3 bucket: {args.s3_bucket}")
        cache_deleted = delete_s3_cache(args.s3_bucket, args.region)
        
        # If cache deletion was requested but failed, log an error but continue
        if not cache_deleted:
            logger.error("Failed to delete cache, but continuing with deployment/test")
        
        # If only cache deletion was requested (no other actions), exit here
        if not args.deploy and not args.test_only and not args.force_rebuild and not args.no_rebuild and not args.logs:
            logger.info("Cache deletion completed. No other operations requested.")
            return 0
    
    # Handle test-only option
    if args.test_only:
        function_name = args.function_name or LAMBDA_CONFIG["FunctionName"]
        logger.info(f"Running test against Lambda function: {function_name}")
        test_lambda_function(function_name, args.region, args.test_event)
        return 0
    
    # Check if we need to build the package
    package_exists = OUTPUT_ZIP.exists()
    
    if package_exists and not args.force_rebuild:
        if args.no_rebuild:
            logger.info("Skipping package rebuild as requested.")
            build_package = False
        else:
            build_package = not input("Package already exists. Skip rebuilding? (y/N): ").lower().startswith('y')
    else:
        build_package = True
    
    if build_package:
        logger.info("Creating Lambda deployment package...")
        
        try:
            # Create package directory
            PACKAGE_DIR.parent.mkdir(parents=True, exist_ok=True)
            
            # Clean and create package directory
            package_dir = clean_directory(PACKAGE_DIR)
            PACKAGE_DIR = package_dir  # Update the global variable
            
            logger.info(f"Using package directory: {PACKAGE_DIR}")
            
            # Install dependencies
            install_dependencies()
            
            # Verify dependencies
            verify_dependencies()
            
            # Copy source files
            copy_source_files()
            
            # Create ZIP file
            create_zip()
            
            # Get ZIP file size
            size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
            logger.info(f"Done! Package size: {size_mb:.2f} MB")
            logger.info(f"Lambda package created at: {OUTPUT_ZIP}")
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
            success = deploy_to_lambda(
                args.function_name, 
                args.region, 
                args.s3_bucket, 
                args.verify,
                args.run_test,
                args.timeout,
                args.test_event
            )
            if not success:
                return 1
        except Exception as e:
            logger.error(f"Error during deployment: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1
    else:
        logger.info("\nTo deploy to AWS Lambda, use:")
        logger.info(f"python {__file__} --deploy [--run-test] [--timeout SECONDS]")
        logger.info("\nTo test an existing Lambda function:")
        logger.info(f"python {__file__} --test-only [--timeout SECONDS] [--test-event PATH]")
        logger.info("\nTo fetch CloudWatch logs:")
        logger.info(f"python {__file__} --logs [--logs-minutes MINUTES]")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 