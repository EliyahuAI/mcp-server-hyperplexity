#!/usr/bin/env python
"""
Independent Config Lambda Deployment Script

This script handles deployment of ONLY the config lambda function.
Separated from the main interface deployment for cleaner management.
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
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory setup
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
CONFIG_LAMBDA_DIR = PROJECT_DIR / "config_lambda"
PACKAGE_DIR = SCRIPT_DIR / "config_lambda_deploy"
OUTPUT_ZIP = SCRIPT_DIR / "config_lambda_deploy.zip"

# Lambda configuration
CONFIG_LAMBDA_CONFIG = {
    "FunctionName": "perplexity-validator-config",
    "Runtime": "python3.9",
    "Handler": "config_lambda_function.lambda_handler",
    "Timeout": 300,  # 5 minutes for AI configuration generation
    "MemorySize": 512,  # Moderate memory for AI API calls
    "Role": "arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7",
    "Environment": {
        "Variables": {
            "S3_UNIFIED_BUCKET": "hyperplexity-storage",  # Unified bucket for all storage
            "S3_DOWNLOAD_BUCKET": "hyperplexity-downloads",  # Separate public downloads bucket for config reviews
            # Legacy variables for compatibility during transition
            "S3_CACHE_BUCKET": "hyperplexity-storage",
            "S3_RESULTS_BUCKET": "hyperplexity-storage",
            "S3_CONFIG_BUCKET": "hyperplexity-downloads"  # Config downloads go to separate bucket
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
            logger.info("Trying alternative cleanup approach...")
            
            try:
                if os.name == 'nt':  # Windows
                    time.sleep(1)
                    cmd = f'rmdir /S /Q "{dir_path}"'
                    logger.info(f"Running command: {cmd}")
                    os.system(cmd)
                else:
                    subprocess.call(['rm', '-rf', str(dir_path)])
            except Exception as e2:
                logger.error(f"Alternative cleanup failed: {e2}")
                # Create new directory with timestamp if cleanup fails
                timestamp = int(time.time())
                global PACKAGE_DIR
                PACKAGE_DIR = dir_path.parent / f"config_lambda_deploy_{timestamp}"
                dir_path = PACKAGE_DIR
    
    dir_path.parent.mkdir(parents=True, exist_ok=True)
    dir_path.mkdir(exist_ok=True)
    return dir_path

def copy_source_files():
    """Copy config lambda source files and dependencies."""
    logger.info("Copying config lambda source files...")
    
    # 1. Copy files from config_lambda directory (main source)
    logger.info(f"Copying from {CONFIG_LAMBDA_DIR}")
    
    # Core config lambda files
    core_files = [
        "config_lambda_function.py",
        "ai_generation_schema.json", 
        "perplexity_schema.py",
        "requirements.txt"
    ]
    
    for file_name in core_files:
        source_file = CONFIG_LAMBDA_DIR / file_name
        if source_file.exists():
            shutil.copy(source_file, PACKAGE_DIR)
            logger.info(f"Copied: {file_name}")
        else:
            logger.warning(f"Core file not found: {file_name}")
    
    # Copy prompts directory
    prompts_source = CONFIG_LAMBDA_DIR / "prompts"
    if prompts_source.exists():
        shutil.copytree(prompts_source, PACKAGE_DIR / "prompts")
        logger.info("Copied prompts directory")
    
    # 2. Copy shared dependencies from src/ (these are the corrected versions)
    logger.info("Copying shared dependencies from src/...")
    
    shared_files = [
        "ai_api_client.py",           # Corrected with debug logging
        "column_config_schema.json",  # Corrected schema without constraints
        "config_validator.py",        # Validation logic
        "shared_table_parser.py"      # Table parsing utilities
    ]
    
    for file_name in shared_files:
        source_file = SRC_DIR / file_name
        if source_file.exists():
            shutil.copy(source_file, PACKAGE_DIR)
            logger.info(f"Copied shared file: {file_name}")
        else:
            logger.error(f"MISSING shared file: {file_name}")

def install_dependencies():
    """Install Python dependencies."""
    logger.info("Installing config lambda dependencies...")
    
    requirements_file = PACKAGE_DIR / "requirements.txt"
    if not requirements_file.exists():
        logger.error("requirements.txt not found in package directory")
        return False
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "-r", str(requirements_file),
            "-t", str(PACKAGE_DIR),
            "--no-cache-dir"
        ])
        logger.info("Dependencies installed successfully")
        
        # Remove requirements.txt from package
        requirements_file.unlink()
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False

def create_package():
    """Create deployment ZIP package."""
    logger.info(f"Creating deployment package: {OUTPUT_ZIP}")
    
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    
    try:
        with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            files_added = 0
            for root, dirs, files in os.walk(PACKAGE_DIR):
                for file in files:
                    file_path = Path(root) / file
                    arc_name = file_path.relative_to(PACKAGE_DIR)
                    zip_file.write(file_path, arc_name)
                    files_added += 1
        
        # Verify package
        if OUTPUT_ZIP.exists():
            zip_size = OUTPUT_ZIP.stat().st_size
            logger.info(f"Package created: {OUTPUT_ZIP}")
            logger.info(f"Package size: {zip_size / (1024*1024):.2f} MB, Files: {files_added}")
            return True
        else:
            logger.error("Package creation failed - file not found")
            return False
            
    except Exception as e:
        logger.error(f"Package creation failed: {e}")
        return False

def deploy_lambda(region="us-east-1"):
    """Deploy or update the config lambda function."""
    logger.info(f"Deploying config lambda to region: {region}")
    
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        # Read package
        with open(OUTPUT_ZIP, 'rb') as f:
            zip_content = f.read()
        
        logger.info(f"Package size: {len(zip_content) / (1024*1024):.2f} MB")
        
        # Check if function exists
        function_exists = False
        try:
            lambda_client.get_function(FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"])
            function_exists = True
            logger.info("Function exists - updating...")
        except lambda_client.exceptions.ResourceNotFoundException:
            logger.info("Function does not exist - creating...")
        
        if function_exists:
            # Update existing function
            response = lambda_client.update_function_code(
                FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"],
                ZipFile=zip_content,
                Publish=True
            )
            logger.info(f"Code updated - Version: {response['Version']}")
            
            # Wait for update to complete
            logger.info("Waiting for code update to complete...")
            lambda_client.get_waiter('function_updated').wait(
                FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"],
                WaiterConfig={'Delay': 5, 'MaxAttempts': 60}
            )
            
            # Update configuration
            lambda_client.update_function_configuration(
                FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"],
                Runtime=CONFIG_LAMBDA_CONFIG["Runtime"],
                Handler=CONFIG_LAMBDA_CONFIG["Handler"],
                Timeout=CONFIG_LAMBDA_CONFIG["Timeout"],
                MemorySize=CONFIG_LAMBDA_CONFIG["MemorySize"],
                Environment=CONFIG_LAMBDA_CONFIG["Environment"]
            )
            logger.info("Function configuration updated")
            
        else:
            # Create new function
            response = lambda_client.create_function(
                FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"],
                Runtime=CONFIG_LAMBDA_CONFIG["Runtime"],
                Role=CONFIG_LAMBDA_CONFIG["Role"],
                Handler=CONFIG_LAMBDA_CONFIG["Handler"],
                Code={'ZipFile': zip_content},
                Timeout=CONFIG_LAMBDA_CONFIG["Timeout"],
                MemorySize=CONFIG_LAMBDA_CONFIG["MemorySize"],
                Environment=CONFIG_LAMBDA_CONFIG["Environment"],
                Publish=True
            )
            logger.info(f"Function created - ARN: {response['FunctionArn']}")
        
        # Verify deployment
        final_config = lambda_client.get_function(FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"])
        logger.info(f"Deployment successful!")
        logger.info(f"Final state: {final_config['Configuration']['State']}")
        logger.info(f"Last modified: {final_config['Configuration']['LastModified']}")
        logger.info(f"Code SHA256: {final_config['Configuration']['CodeSha256']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_deployment(region="us-east-1"):
    """Test the deployed lambda function."""
    logger.info("Testing deployed lambda function...")
    
    # Simple test payload
    test_payload = {
        "table_analysis": {
            "basic_info": {
                "filename": "test.xlsx",
                "shape": [10, 3],
                "column_names": ["Name", "Email", "Department"]
            },
            "column_analysis": {
                "Name": {"data_type": "string", "fill_rate": 1.0, "sample_values": ["John", "Jane"]},
                "Email": {"data_type": "string", "fill_rate": 0.95, "sample_values": ["john@test.com", "jane@test.com"]},
                "Department": {"data_type": "string", "fill_rate": 1.0, "sample_values": ["IT", "HR"]}
            },
            "domain_info": {"likely_domain": "employee_data", "confidence": 0.8}
        },
        "instructions": "Create a basic configuration for this employee table",
        "session_id": f"test_{int(time.time())}"
    }
    
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        response = lambda_client.invoke(
            FunctionName=CONFIG_LAMBDA_CONFIG["FunctionName"],
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            body = json.loads(result['body']) if isinstance(result.get('body'), str) else result.get('body', {})
            
            if body.get('success'):
                logger.info("TEST PASSED - Config generation successful!")
                if body.get('updated_config'):
                    config = body['updated_config']
                    logger.info(f"Generated {len(config.get('validation_targets', []))} validation targets")
                return True
            else:
                logger.error(f"TEST FAILED - {body.get('error', 'Unknown error')}")
                return False
        else:
            logger.error(f"TEST FAILED - Lambda returned status {response['StatusCode']}")
            logger.error(f"Response: {result}")
            return False
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

def main():
    """Main deployment function."""
    parser = argparse.ArgumentParser(description='Deploy Config Lambda independently')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--test', action='store_true', help='Test deployment after creation')
    parser.add_argument('--build-only', action='store_true', help='Only build package, do not deploy')
    parser.add_argument('--force-rebuild', action='store_true', help='Force rebuild package even if it exists')
    parser.add_argument('--deploy', action='store_true', help='Deploy the Lambda function (default behavior unless --build-only is specified)')
    args = parser.parse_args()
    
    logger.info("=== Independent Config Lambda Deployment ===")
    
    try:
        # Check if package exists and if we should rebuild
        should_build = args.force_rebuild or not OUTPUT_ZIP.exists()
        
        if should_build:
            logger.info("Building deployment package...")
            
            # Clean and prepare
            global PACKAGE_DIR
            PACKAGE_DIR = clean_directory(PACKAGE_DIR)
            
            # Copy source files
            copy_source_files()
            
            # Install dependencies
            if not install_dependencies():
                return 1
            
            # Create package
            if not create_package():
                return 1
        else:
            logger.info(f"Using existing package: {OUTPUT_ZIP}")
            logger.info("Use --force-rebuild to rebuild the package")
        
        if args.build_only:
            logger.info(f"Build complete. Package: {OUTPUT_ZIP}")
            return 0
        
        # Deploy (default behavior unless --build-only is specified)
        if not args.build_only:
            if not deploy_lambda(args.region):
                return 1
        
        # Test if requested
        if args.test:
            if test_deployment(args.region):
                logger.info("All tests passed!")
            else:
                logger.warning("Tests failed, but deployment was successful")
        
        logger.info("=== Deployment Complete ===")
        return 0
        
    except Exception as e:
        logger.error(f"Deployment script failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())