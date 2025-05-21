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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory setup
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
PACKAGE_DIR = SCRIPT_DIR / "package"
OUTPUT_ZIP = SCRIPT_DIR / "lambda_package.zip"

# Lambda configuration
LAMBDA_CONFIG = {
    "FunctionName": "perplexity-validator",
    "Runtime": "python3.9",
    "Handler": "lambda_function.lambda_handler",
    "Timeout": 180,  # 3 minutes in seconds
    "MemorySize": 512,  # MB
    "Role": "arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7",
    "Environment": {
        "Variables": {
            "S3_CACHE_BUCKET": "perplexity-cache"
        }
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
    logger.info(f"Installing dependencies from {PROJECT_DIR / 'requirements-lambda.txt'}...")
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "-r", str(PROJECT_DIR / "requirements-lambda.txt"),
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
                    "--no-cache-dir"
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
                "--no-cache-dir"
            ])
    
    if verify_file.exists():
        verify_file.unlink()

def copy_source_files():
    """Copy necessary source files."""
    logger.info("Copying source files...")
    # Copy lambda_function.py
    lambda_source = SRC_DIR / "lambda_function.py"
    shutil.copy(lambda_source, PACKAGE_DIR)
    # Copy schema_validator.py
    schema_source = SRC_DIR / "schema_validator.py"
    shutil.copy(schema_source, PACKAGE_DIR)
    # Copy prompt_loader.py
    prompt_loader = SRC_DIR / "prompt_loader.py"
    if prompt_loader.exists():
        shutil.copy(prompt_loader, PACKAGE_DIR)
        logger.info("Copied prompt_loader.py")
    else:
        logger.warning(f"prompt_loader.py not found at {prompt_loader}")
    
    # Copy url_extractor.py
    url_extractor = SRC_DIR / "url_extractor.py"
    if url_extractor.exists():
        shutil.copy(url_extractor, PACKAGE_DIR)
        logger.info("Copied url_extractor.py")
    else:
        logger.warning(f"url_extractor.py not found at {url_extractor}")
    
    # Copy prompts.yml
    prompts_yml = PROJECT_DIR / "prompts.yml"
    if prompts_yml.exists():
        shutil.copy(prompts_yml, PACKAGE_DIR)
        logger.info("Copied prompts.yml")
    else:
        logger.warning(f"prompts.yml not found at {prompts_yml}")

def create_zip():
    """Create deployment zip file."""
    logger.info(f"Creating ZIP file: {OUTPUT_ZIP}")
    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(PACKAGE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, PACKAGE_DIR)
                zipf.write(file_path, arcname)

def deploy_to_lambda(function_name=None, region=None, s3_bucket=None, verify=False, run_test=False):
    """Deploy the Lambda package to AWS."""
    if function_name:
        LAMBDA_CONFIG["FunctionName"] = function_name
    
    if s3_bucket:
        LAMBDA_CONFIG["Environment"]["Variables"]["S3_CACHE_BUCKET"] = s3_bucket

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
            
            response = lambda_client.update_function_code(**update_code_args)
            logger.info(f"Function code updated successfully. Version: {response.get('Version')}")
            
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
                    }
                    
                    response = lambda_client.update_function_configuration(**update_config_args)
            logger.info("Function configuration updated successfully.")
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
            }
            
            response = lambda_client.create_function(**create_function_args)
            logger.info(f"New function created successfully. ARN: {response.get('FunctionArn')}")
        
        logger.info("\nDeployment completed successfully!")
        logger.info(f"Lambda function URL: https://console.aws.amazon.com/lambda/home?region={region or 'us-east-1'}#/functions/{LAMBDA_CONFIG['FunctionName']}")
        
        # Run test if requested
        if run_test:
            logger.info("\nRunning test after deployment...")
            test_lambda_function(LAMBDA_CONFIG["FunctionName"], region)
        
        return True
        
    except Exception as e:
        logger.error(f"Error deploying to Lambda: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_lambda_function(function_name, region=None):
    """Test the Lambda function with the enhanced test event."""
    logger.info(f"Testing Lambda function: {function_name}")
    
    try:
        # Load test event
        test_event_path = PROJECT_DIR / "test_events" / "enhanced_test_event.json"
        with open(test_event_path, 'r') as f:
            test_event = json.load(f)
        
        # Initialize Lambda client
        lambda_client = boto3.client('lambda', region_name=region)
        
        logger.info("Invoking Lambda function...")
        
        # Invoke Lambda function
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(test_event)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        # Log the full response for debugging
        logger.info("Full Lambda response:")
        logger.info(json.dumps(response_payload, indent=2))
        
        if response_payload.get('statusCode') == 200:
            results = response_payload['body']
            logger.info("Validation completed successfully!")
            logger.info(f"Cache stats: {results['cache_stats']}")
            
            # Print validation results
            for row_idx, row_results in results['validation_results'].items():
                logger.info(f"\nRow {row_idx} Results:")
                for target, result in row_results.items():
                    if target not in ['next_check', 'reasons']:
                        logger.info(f"  {target}:")
                        logger.info(f"    Value: {result['value']}")
                        logger.info(f"    Confidence: {result['confidence']} ({result['confidence_level']})")
                        logger.info(f"    Sources: {result['sources']}")
                        if result['quote']:
                            logger.info(f"    Quote: {result['quote']}")
                
                logger.info(f"  Next Check: {row_results['next_check']}")
                logger.info(f"  Reasons: {row_results['reasons']}")
                
            # Return after processing all rows (fixed indentation)
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
            
            return False
        
    except Exception as e:
        logger.error(f"Error testing Lambda: {str(e)}")
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        return False

def delete_s3_cache(bucket_name, region=None):
    """Delete all validation cache objects from the S3 bucket."""
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=region)
        
        logger.info(f"Listing objects in s3://{bucket_name}/validation_cache/")
        
        # List objects with validation_cache/ prefix
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix='validation_cache/')
        
        total_objects = 0
        deleted_objects = 0
        
        for page in pages:
            if 'Contents' not in page:
                logger.info("No cache objects found.")
                return True  # Return True even when no objects are found (success)
                
            objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]
            total_objects += len(objects_to_delete)
            
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
        
        logger.info(f"Successfully deleted {deleted_objects}/{total_objects} cache objects from s3://{bucket_name}/validation_cache/")
        
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
    parser.add_argument('--s3-bucket', default='perplexity-cache', help='S3 bucket for caching (default: perplexity-cache)')
    parser.add_argument('--verify', action='store_true', help='Verify the Lambda function after deployment')
    parser.add_argument('--force-rebuild', action='store_true', help='Force rebuilding the package even if it exists')
    parser.add_argument('--no-rebuild', action='store_true', help='Skip rebuilding the package if it exists')
    parser.add_argument('--run-test', action='store_true', help='Run a test of the function after deployment')
    parser.add_argument('--test-only', action='store_true', help='Only run a test without deploying')
    parser.add_argument('--delete-cache', action='store_true', help='Delete all validation cache objects from the S3 bucket')
    args = parser.parse_args()
    
    # Handle delete-cache option
    if args.delete_cache:
        logger.info(f"Deleting validation cache from S3 bucket: {args.s3_bucket}")
        cache_deleted = delete_s3_cache(args.s3_bucket, args.region)
        
        # If cache deletion was requested but failed, log an error but continue
        if not cache_deleted:
            logger.error("Failed to delete cache, but continuing with deployment/test")
        
        # If only cache deletion was requested (no other actions), exit here
        if not args.deploy and not args.test_only and not args.force_rebuild and not args.no_rebuild:
            logger.info("Cache deletion completed. No other operations requested.")
            return 0
    
    # Handle test-only option
    if args.test_only:
        function_name = args.function_name or LAMBDA_CONFIG["FunctionName"]
        logger.info(f"Running test against Lambda function: {function_name}")
        test_lambda_function(function_name, args.region)
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
                args.run_test
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
        logger.info(f"python {__file__} --deploy [--run-test]")
        logger.info("\nTo test an existing Lambda function:")
        logger.info(f"python {__file__} --test-only --function-name perplexity-validator")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 