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
import random  # Add import for random
import re  # Add import for re

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
            print(f"Cleaning directory: {dir_path}")
            # Try to remove directory safely
            shutil.rmtree(dir_path)
        except PermissionError as e:
            print(f"Permission error when cleaning directory: {e}")
            print("Trying to use a different approach...")
            
            try:
                # Use os.system to run rmdir on Windows which can handle locked files better
                if os.name == 'nt':  # Windows
                    # Wait a moment to let any processes release files
                    time.sleep(1)
                    # Use /S for recursive deletion and /Q for quiet mode
                    cmd = f'rmdir /S /Q "{dir_path}"'
                    print(f"Running command: {cmd}")
                    os.system(cmd)
                else:
                    # On Unix, try with force flag
                    subprocess.call(['rm', '-rf', str(dir_path)])
            except Exception as e2:
                print(f"Second attempt failed: {e2}")
                print("Continuing with a new directory name...")
                # If we can't clean it, use a new directory with timestamp
                timestamp = int(time.time())
                global PACKAGE_DIR
                PACKAGE_DIR = dir_path.parent / f"package_{timestamp}"
                dir_path = PACKAGE_DIR
    
    # Create parent directories if they don't exist
    dir_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create the directory
    dir_path.mkdir(exist_ok=True)
    return dir_path

def install_dependencies():
    """Install dependencies to package directory."""
    print(f"Installing dependencies from {PROJECT_DIR / 'requirements-lambda.txt'}...")
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "-r", str(PROJECT_DIR / "requirements-lambda.txt"),
                "-t", str(PACKAGE_DIR),
                "--no-cache-dir"
            ])
            print("Dependencies installed successfully.")
            break
        except subprocess.CalledProcessError as e:
            print(f"Error installing dependencies (attempt {attempt}/{max_attempts}): {e}")
            if attempt == max_attempts:
                raise
            print("Retrying in 2 seconds...")
            time.sleep(2)
    
    # Ensure typing_extensions is installed (critical for Lambda)
    print("Ensuring typing_extensions is installed (critical dependency)...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "typing_extensions>=4.0.0",
            "-t", str(PACKAGE_DIR),
            "--no-cache-dir"
        ])
    except subprocess.CalledProcessError:
        print("Error installing typing_extensions directly. Trying alternate method...")
        try:
            # Try with pip download then copy
            temp_dir = Path("temp_deps")
            temp_dir.mkdir(exist_ok=True)
            subprocess.check_call([
                sys.executable, "-m", "pip", "download",
                "typing_extensions>=4.0.0",
                "-d", str(temp_dir)
            ])
            
            # Find and extract the wheel file
            for wheel_file in temp_dir.glob("*.whl"):
                print(f"Found wheel: {wheel_file}")
                import zipfile
                with zipfile.ZipFile(wheel_file, 'r') as wheel_zip:
                    wheel_zip.extractall(PACKAGE_DIR)
                print(f"Extracted typing_extensions from wheel.")
                break
        except Exception as e:
            print(f"Alt installation method failed: {e}")
    
    # Ensure all aiohttp dependencies are installed
    print("Installing aiohttp and all its dependencies...")
    aiohttp_deps = [
        "aiohttp>=3.8.0",
        "async_timeout>=4.0.0",
        "attrs>=21.2.0",
        "multidict>=6.0.0",
        "yarl>=1.8.0",
        "frozenlist>=1.3.0",
        "idna>=3.3"
    ]
    
    for dep in aiohttp_deps:
        print(f"Installing {dep}...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                dep,
                "-t", str(PACKAGE_DIR),
                "--no-cache-dir"
            ])
        except subprocess.CalledProcessError:
            print(f"Error installing {dep}. Will try to continue anyway.")

def verify_dependencies():
    """Verify that all critical dependencies are properly installed."""
    print("Verifying critical dependencies...")
    
    # List of critical dependencies to check
    critical_deps = [
        "aiohttp", 
        "typing_extensions", 
        "python_dateutil",
        "async_timeout",
        "attrs",
        "multidict",
        "yarl",
        "frozenlist",
        "idna"
    ]
    
    # Create a verification file to import and test dependencies
    verify_file = PACKAGE_DIR / "verify_deps.py"
    with open(verify_file, "w") as f:
        f.write("# Dependency verification\n")
        for dep in critical_deps:
            f.write(f"import {dep.replace('-', '_')}\n")
            f.write(f"print(f'Successfully imported {dep}')\n")
    
    # Try to run the verification file
    try:
        print(f"Testing imports in the package directory...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE_DIR)
        
        result = subprocess.run(
            [sys.executable, str(verify_file)],
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"All critical dependencies verified successfully.")
            for line in result.stdout.splitlines():
                print(f"  {line}")
        else:
            print(f"Warning: Some dependencies failed verification!")
            print(f"Error output: {result.stderr}")
            print("Installing missing dependencies directly...")
            
            # Install critical dependencies directly
            for dep in critical_deps:
                print(f"Ensuring {dep} is installed...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    dep,
                    "-t", str(PACKAGE_DIR),
                    "--no-cache-dir"
                ])
    except Exception as e:
        print(f"Error during dependency verification: {str(e)}")
        print("Proceeding with direct installation of critical dependencies...")
        
        # Install critical dependencies directly
        for dep in critical_deps:
            print(f"Installing {dep} directly...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                dep,
                "-t", str(PACKAGE_DIR),
                "--no-cache-dir"
            ])
    
    # Remove verification file
    if verify_file.exists():
        verify_file.unlink()

def copy_source_files(use_layer=False):
    """Copy necessary source files."""
    print("Copying source files...")
    
    if use_layer:
        # For layer deployment, create a minimal package
        shutil.copy(SRC_DIR / "schema_validator.py", PACKAGE_DIR)
        
        # When using layer, we're only copying lambda_function.py directly
        # as all dependencies will be in the layer
        shutil.copy(SRC_DIR / "lambda_function.py", PACKAGE_DIR)
    else:
        # Standard deployment - copy all source files
        shutil.copy(SRC_DIR / "lambda_function.py", PACKAGE_DIR)
        shutil.copy(SRC_DIR / "schema_validator.py", PACKAGE_DIR)

def create_zip():
    """Create deployment zip file."""
    print(f"Creating ZIP file: {OUTPUT_ZIP}")
    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(PACKAGE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, PACKAGE_DIR)
                zipf.write(file_path, arcname)

def find_existing_layer(layer_name, region=None):
    """Check if a Lambda layer already exists with the given name and return its ARN."""
    try:
        print(f"Checking for existing Lambda layer: {layer_name}")
        lambda_client = boto3.client('lambda', region_name=region)
        
        # List the versions of the layer
        response = lambda_client.list_layer_versions(LayerName=layer_name)
        
        if response.get('LayerVersions'):
            # Get the latest version
            latest_layer = response['LayerVersions'][0]
            layer_arn = latest_layer['LayerVersionArn']
            print(f"Found existing layer: {layer_arn}")
            return layer_arn
        else:
            print(f"No existing layer found with name: {layer_name}")
            return None
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Layer {layer_name} does not exist")
        return None
    except Exception as e:
        print(f"Error checking for existing layer: {str(e)}")
        return None

def test_lambda_function(function_name, region=None, detailed=True, test_caching=True):
    """Test the Lambda function with a sample event and display results."""
    print(f"\nRunning test for Lambda function: {function_name}")
    
    lambda_client = boto3.client('lambda', region_name=region)
    
    # Create a simple test event - similar to what we'd use in actual validation
    test_event = {
        "config": {
            "primary_key": ["id"],
            "validation_targets": [
                {
                    "column": "name",
                    "validation_type": "string",
                    "rules": {
                        "min_length": 2,
                        "max_length": 50
                    },
                    "description": "Test validation of name field"
                }
            ]
        },
        "validation_data": {
            "rows": [
                {
                    "id": "test_id_123",
                    "name": "John Smith"
                }
            ]
        }
    }
    
    # Generate a random test data for the first run to avoid cache hits
    random_suffix = random.randint(10000, 99999)
    timestamp = int(time.time())
    
    # Create a deep copy with substantial changes to ensure a different cache hash
    first_test_event = {
        "config": test_event["config"].copy(),
        "validation_data": {
            "rows": [
                {
                    "id": f"test_id_{random_suffix}_{timestamp}",
                    "name": f"John Doe {random_suffix}", 
                    "email": f"test{random_suffix}@example.com"  # Add extra field to further ensure uniqueness
                }
            ]
        },
        # Add debug flag to request printing of cache key generation details
        "debug_options": {
            "print_cache_key_details": True,
            "test_run_id": f"debug_{timestamp}_{random_suffix}"
        }
    }
    
    print(f"Invoking function with randomized test data:")
    print(f"  - ID: {first_test_event['validation_data']['rows'][0]['id']}")
    print(f"  - Name: {first_test_event['validation_data']['rows'][0]['name']}")
    print(f"  - Email: {first_test_event['validation_data']['rows'][0]['email']}")
    print(f"  - Debug mode: enabled (will print cache key details)")
    
    try:
        # First test run with randomized data
        start_time = time.time()
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',  # Wait for response
            LogType='Tail',  # Include logs
            Payload=json.dumps(first_test_event)
        )
        elapsed_time = time.time() - start_time
        
        # Get execution logs
        logs = base64.b64decode(response.get('LogResult', '')).decode('utf-8')
        
        # Get the response payload
        response_payload = json.loads(response['Payload'].read())
        
        # Extract and print the cache key information from logs if available
        cache_key_info = None
        if logs:
            print("\nSearching logs for cache key generation details...")
            for line in logs.splitlines():
                if "cache key" in line.lower() or "hash input" in line.lower() or "generating hash" in line.lower():
                    print(f"  {line}")
                    # Try to extract the actual hash input if possible
                    if "hash input" in line.lower():
                        cache_key_info = line
        
        if not cache_key_info:
            print("  No detailed cache key information found in logs.")
            print("  The Lambda function may need to be modified to print cache key generation details.")
        
        # Check if the function executed successfully
        cache_used = False
        if response.get('StatusCode') == 200:
            if response_payload.get('statusCode') == 200:
                print(f"TEST PASSED! Function executed successfully in {elapsed_time:.2f} seconds")
                
                if detailed:
                    print("\nTest Results:")
                    try:
                        results = response_payload.get('body', {}).get('results', {})
                        for column, result in results.items():
                            if isinstance(result, (list, tuple)) and len(result) >= 3:
                                value, confidence, message = result[:3]
                                print(f"\n  {column}:")
                                print(f"    Value: {value}")
                                print(f"    Confidence: {confidence}")
                                print(f"    Message: {message}")
                            else:
                                print(f"  {column}: {result}")
                    except Exception as e:
                        print(f"Error parsing results: {str(e)}")
                    
                    # Check if cache was used in the first run
                    if logs:
                        cache_used = False
                        cache_confirmed_miss = False
                        
                        for line in logs.splitlines():
                            # Only consider real cache hits, not just cache checks
                            if any(cache_hit_term in line.lower() for cache_hit_term in [
                                "returning cached", "cached validation results", "using cached"
                            ]):
                                cache_used = True
                                print("\n[WARNING] Cache was already used in the first test. This means either:")
                                print("   - The test event was previously run and cached")
                                print("   - Cache detection logic might need refinement")
                                # If we find a cache hit, extract and show the cache filename
                                cache_file_match = re.search(r'validation_results/([a-f0-9]+\.json)', line)
                                if cache_file_match:
                                    cache_file = cache_file_match.group(1)
                                    print(f"   - Cache file used: {cache_file}")
                                break
                            
                            # Check if "No cache found" is mentioned, which confirms a cache miss
                            elif "no cache found" in line.lower():
                                cache_confirmed_miss = True
                        
                        if not cache_used and cache_confirmed_miss:
                            print("\n[SUCCESS] Confirmed: No cache was used for the first test (explicit cache miss)")
                        
                        # Print relevant logs
                        print("\nExecution Logs (excerpt):")
                        # Extract most relevant log lines (API calls, cache info)
                        relevant_logs = []
                        log_lines = logs.splitlines()
                        for line in log_lines:
                            if any(term in line.lower() for term in [
                                'api call', 'cache', 'validation', 'perplexity', 'error', 'warning',
                                'hash', 'key'
                            ]):
                                relevant_logs.append(line)
                        
                        if relevant_logs:
                            for line in relevant_logs[-15:]:  # Show more relevant lines
                                print(f"  {line}")
                        else:
                            print("  No relevant logs found")
                
                # If cache testing is requested and cache wasn't already used in the first run
                if test_caching and not cache_used:
                    print("\nRunning second test to verify caching...")
                    
                    # Create a copy of the first test event but with same ID to ensure cache hit
                    # Leave all other random fields the same to ensure the cache key matches
                    second_test_event = first_test_event.copy()
                    
                    # Remove debug options for second run
                    if "debug_options" in second_test_event:
                        second_test_event["debug_options"]["print_cache_key_details"] = False
                    
                    print(f"Using identical test data for cache test")
                    
                    # Sleep briefly to ensure Lambda function finishes processing the first request
                    time.sleep(5)  # Increased sleep time to ensure caching completes
                    
                    # Second test run with the identical event (should use cache)
                    cache_test_start = time.time()
                    cache_test_response = lambda_client.invoke(
                        FunctionName=function_name,
                        InvocationType='RequestResponse',
                        LogType='Tail',
                        Payload=json.dumps(second_test_event)
                    )
                    cache_test_time = time.time() - cache_test_start
                    
                    # Get execution logs for the cache test
                    cache_logs = base64.b64decode(cache_test_response.get('LogResult', '')).decode('utf-8')
                    
                    # Get the response payload
                    cache_response_payload = json.loads(cache_test_response['Payload'].read())
                    
                    # Check if the second call was successful
                    if cache_test_response.get('StatusCode') == 200 and cache_response_payload.get('statusCode') == 200:
                        # Calculate speedup
                        speedup = elapsed_time / cache_test_time if cache_test_time > 0 else 0
                        
                        # Check if cache was used
                        cache_found = False
                        cache_miss = False
                        
                        for line in cache_logs.splitlines():
                            # Only look for explicit cache hit messages
                            if any(cache_hit_term in line.lower() for cache_hit_term in [
                                "returning cached", "cached validation results", "from cache", "using cached"
                            ]):
                                cache_found = True
                                break
                            
                            # Check for explicit cache miss messages
                            elif "no cache found" in line.lower():
                                cache_miss = True
                        
                        # Determine if caching is working based on timing and logs
                        if cache_found:
                            print(f"CACHE TEST PASSED! Second execution in {cache_test_time:.2f} seconds (Speed-up: {speedup:.2f}x)")
                            print("   [SUCCESS] Cache was successfully used for the second request (explicit cache hit)")
                        elif cache_test_time < elapsed_time * 0.5 and not cache_miss:  # Significantly faster (50% of original time)
                            print(f"CACHE TEST LIKELY PASSED! Second execution in {cache_test_time:.2f} seconds (Speed-up: {speedup:.2f}x)")
                            print("   No explicit cache hit message found, but execution time indicates cache was used")
                        elif cache_miss:
                            print(f"[ERROR] CACHE TEST FAILED! Second execution in {cache_test_time:.2f} seconds")
                            print("   Explicit 'No cache found' message indicates caching didn't work")
                        else:
                            print(f"[WARNING] Cache test inconclusive: Second execution took {cache_test_time:.2f} seconds (vs {elapsed_time:.2f} for first run)")
                            print("   No explicit cache usage detected in logs")
                        
                        # Print relevant cache test logs
                        print("\nCache Test Logs (excerpt):")
                        cache_relevant_logs = []
                        for line in cache_logs.splitlines():
                            if any(term in line.lower() for term in [
                                'api call', 'cache', 'validation', 'perplexity', 'error', 'warning',
                                'hash', 'key'
                            ]):
                                cache_relevant_logs.append(line)
                        
                        if cache_relevant_logs:
                            for line in cache_relevant_logs[-15:]:  # Show more relevant lines
                                print(f"  {line}")
                        else:
                            print("  No relevant cache logs found")
                    else:
                        print(f"[ERROR] Second execution failed! Status: {cache_test_response.get('StatusCode')}")
                
                return True
            else:
                print(f"[ERROR] Test failed! Function returned error: {response_payload.get('body')}")
        else:
            print(f"[ERROR] Test failed! Execution error: {response.get('FunctionError')}")
        
        if detailed and logs:
            print("\nError Logs:")
            for line in logs.splitlines()[-10:]:  # Show last 10 lines
                print(f"  {line}")
        
        return False
    except Exception as e:
        print(f"[ERROR] Error testing Lambda function: {str(e)}")
        return False

def deploy_to_lambda(function_name=None, region=None, s3_bucket=None, verify=False, use_layer=False, layer_name=None, run_test=False):
    """Deploy the Lambda package to AWS."""
    if function_name:
        LAMBDA_CONFIG["FunctionName"] = function_name
    
    if s3_bucket:
        LAMBDA_CONFIG["Environment"]["Variables"]["S3_CACHE_BUCKET"] = s3_bucket

    # Create AWS Lambda client
    lambda_client = boto3.client('lambda', region_name=region)
    
    print(f"Deploying to Lambda function: {LAMBDA_CONFIG['FunctionName']}")
    
    deployment_successful = False
    layer_arn = None
    
    try:
        # Check for existing layer or publish a new one
        if use_layer:
            layer_name = layer_name or f"{function_name or LAMBDA_CONFIG['FunctionName']}-layer"
            # Try to find existing layer first
            layer_arn = find_existing_layer(layer_name, region)
            
            if not layer_arn:
                try:
                    print("Creating Lambda Layer for dependencies...")
                    layer_zip = create_layer_package()
                    if not layer_zip or not layer_zip.exists():
                        print("[WARNING] Layer package creation failed. Continuing without layer...")
                    else:
                        try:
                            print(f"Publishing layer: {layer_name}")
                            layer_arn = publish_layer(layer_zip, layer_name, region)
                        except Exception as e:
                            print(f"[WARNING] Error publishing layer: {str(e)}")
                            print("Continuing deployment without layer...")
                except Exception as e:
                    print(f"[WARNING] Error creating layer package: {str(e)}")
                    print("Continuing deployment without layer...")
        
        # Check if function exists
        try:
            lambda_client.get_function(FunctionName=LAMBDA_CONFIG["FunctionName"])
            function_exists = True
            print(f"Lambda function {LAMBDA_CONFIG['FunctionName']} exists. Updating...")
        except lambda_client.exceptions.ResourceNotFoundException:
            function_exists = False
            print(f"Lambda function {LAMBDA_CONFIG['FunctionName']} does not exist. Creating new function...")
        except Exception as e:
            print(f"[WARNING] Error checking if function exists: {str(e)}")
            print("Assuming function does not exist and proceeding with creation...")
            function_exists = False
        
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
            print(f"Function code updated successfully. Version: {response.get('Version')}")
            
            # Wait for the update to complete before trying to update configuration
            print("Waiting for code update to complete before updating configuration...")
            for i in range(5):
                time.sleep(3)  # Wait 3 seconds between checks
                try:
                    # Check function state
                    function_info = lambda_client.get_function(
                        FunctionName=LAMBDA_CONFIG["FunctionName"]
                    )
                    state = function_info['Configuration']['State']
                    if state == 'Active':
                        print(f"Function is now in Active state. Ready to update configuration.")
                        break
                    else:
                        print(f"Function state: {state}. Waiting...")
                except Exception as e:
                    print(f"Error checking function state: {str(e)}")
            
            # Update function configuration with retry logic
            for attempt in range(3):
                try:
                    print(f"Updating function configuration (attempt {attempt+1})...")
                    update_config_args = {
                        'FunctionName': LAMBDA_CONFIG["FunctionName"],
                        'Runtime': LAMBDA_CONFIG["Runtime"],
                        'Role': LAMBDA_CONFIG["Role"],
                        'Handler': LAMBDA_CONFIG["Handler"],
                        'Timeout': LAMBDA_CONFIG["Timeout"],
                        'MemorySize': LAMBDA_CONFIG["MemorySize"],
                        'Environment': LAMBDA_CONFIG["Environment"],
                    }
                    
                    # Add layer if available
                    if layer_arn:
                        update_config_args['Layers'] = [layer_arn]
                    
                    response = lambda_client.update_function_configuration(**update_config_args)
                    print(f"Function configuration updated successfully.")
                    break
                except lambda_client.exceptions.ResourceConflictException as e:
                    if attempt < 2:
                        print(f"Resource conflict: {str(e)}. Waiting before retrying...")
                        time.sleep(5)  # Wait 5 seconds before retrying
                    else:
                        print(f"Failed to update configuration after 3 attempts: {str(e)}")
                        print("The function code has been updated, but configuration changes were not applied.")
                        print("You may need to update the configuration manually via the AWS console.")
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
            
            # Add layer if available
            if layer_arn:
                create_function_args['Layers'] = [layer_arn]
            
            response = lambda_client.create_function(**create_function_args)
            print(f"New function created successfully. ARN: {response.get('FunctionArn')}")
        
        print("\nDeployment completed successfully!")
        print(f"Lambda function URL: https://console.aws.amazon.com/lambda/home?region={region or 'us-east-1'}#/functions/{LAMBDA_CONFIG['FunctionName']}")
        
        deployment_successful = True
        
    except Exception as e:
        print(f"Error deploying to Lambda: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    
    # Run tests if requested
    if deployment_successful and run_test:
        print("\nWaiting for function to stabilize before testing...")
        time.sleep(5)
        test_lambda_function(LAMBDA_CONFIG["FunctionName"], region)
    # Verify the function if requested
    elif deployment_successful and verify:
        verified = verify_lambda_function(LAMBDA_CONFIG["FunctionName"], region)
        if verified:
            print("✅ Lambda function is working correctly.")
        else:
            print("⚠️ Lambda function verification failed. Check logs for more details.")

def verify_lambda_function(function_name, region=None):
    """Verify that the Lambda function is working by invoking it with a test event."""
    print(f"Verifying Lambda function {function_name}...")
    
    lambda_client = boto3.client('lambda', region_name=region)
    
    # Generate unique test data with timestamp to ensure no cache hits
    random_suffix = random.randint(10000, 99999)
    timestamp = int(time.time())
    
    # Create a test event with multiple unique fields
    test_event = {
        "config": {
            "primary_key": ["id"],
            "validation_targets": [
                {
                    "column": "test_field",
                    "validation_type": "string",
                    "rules": {
                        "min_length": 2,
                        "max_length": 100
                    },
                    "description": f"Test validation {random_suffix}"  # Add randomness to description
                }
            ]
        },
        "validation_data": {
            "rows": [
                {
                    "id": f"verify_test_{timestamp}_{random_suffix}",
                    "test_field": f"Verification Test Value {random_suffix}",
                    "extra_field": f"Extra data {timestamp}",  # Additional field for uniqueness
                    "random_number": random_suffix  # Numeric field for more variation
                }
            ]
        },
        "metadata": {  # Add metadata section for even more uniqueness
            "test_run_id": f"verify_{timestamp}_{random_suffix}",
            "timestamp": timestamp
        }
    }
    
    try:
        print("Waiting for the function to be fully ready...")
        time.sleep(10)  # Wait for the function to be fully ready
        
        print(f"Invoking Lambda function with unique verification data:")
        print(f"  - Test ID: {test_event['validation_data']['rows'][0]['id']}")
        print(f"  - Test value: {test_event['validation_data']['rows'][0]['test_field']}")
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(test_event)
        )
        
        # Read the response payload
        payload = json.loads(response['Payload'].read())
        
        if response.get('StatusCode') == 200:
            if payload.get('statusCode') == 200:
                print(f"✅ Lambda function verified successfully!")
                return True
            else:
                print(f"⚠️ Lambda function returned non-200 status: {payload.get('statusCode')}")
                print(f"Error: {payload.get('body')}")
        else:
            print(f"⚠️ Lambda invocation failed with status: {response.get('StatusCode')}")
            print(f"Error: {payload}")
        
        return False
    except Exception as e:
        print(f"⚠️ Error verifying Lambda function: {str(e)}")
        return False

def create_layer_package():
    """Create a separate Lambda layer package with all dependencies."""
    print("Creating Lambda layer with all dependencies...")
    
    # Define the layer directories
    LAYER_DIR = SCRIPT_DIR / "lambda-layer"
    PYTHON_DIR = LAYER_DIR / "python"
    LAYER_ZIP = SCRIPT_DIR / "lambda_layer.zip"
    
    # Ensure directories exist
    if LAYER_DIR.exists():
        try:
            shutil.rmtree(LAYER_DIR)
        except PermissionError:
            print(f"Permission error when removing {LAYER_DIR}")
            # Use clean_directory since it has better error handling
            clean_directory(LAYER_DIR)
    
    # Create directories
    LAYER_DIR.mkdir(parents=True, exist_ok=True)
    PYTHON_DIR.mkdir(parents=True, exist_ok=True)
    
    # Install all dependencies to the layer directory
    print(f"Installing dependencies to layer from {PROJECT_DIR / 'requirements-lambda.txt'}...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "-r", str(PROJECT_DIR / 'requirements-lambda.txt'),
        "-t", str(PYTHON_DIR),
        "--no-cache-dir"
    ])
    
    # Create ZIP file
    print(f"Creating layer ZIP file: {LAYER_ZIP}")
    try:
        with zipfile.ZipFile(LAYER_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(LAYER_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, LAYER_DIR)
                    zipf.write(file_path, arcname)
        
        if not LAYER_ZIP.exists() or LAYER_ZIP.stat().st_size == 0:
            print(f"⚠️ Error: Layer ZIP file is empty or not created: {LAYER_ZIP}")
            return None
            
        # Get ZIP file size
        size_mb = LAYER_ZIP.stat().st_size / (1024 * 1024)
        print(f"Layer package size: {size_mb:.2f} MB")
        
        # Verify zip content
        with zipfile.ZipFile(LAYER_ZIP, 'r') as zipf:
            file_count = len(zipf.namelist())
            print(f"Layer ZIP contains {file_count} files")
            if file_count == 0:
                print(f"⚠️ Warning: Layer ZIP file has no content")
                return None
        
        return LAYER_ZIP
    except Exception as e:
        print(f"Error creating layer ZIP: {str(e)}")
        return None

def publish_layer(layer_zip, layer_name, region=None):
    """Publish the Lambda layer to AWS."""
    print(f"Publishing Lambda layer {layer_name}...")
    
    # Validate layer_zip
    if not layer_zip or not os.path.exists(layer_zip):
        print(f"⚠️ Error: Layer ZIP file not found: {layer_zip}")
        return None
    
    try:
        # Validate zip content
        with zipfile.ZipFile(layer_zip, 'r') as zipf:
            file_count = len(zipf.namelist())
            if file_count == 0:
                print(f"⚠️ Error: Layer ZIP file is empty")
                return None
    except Exception as e:
        print(f"⚠️ Error validating layer ZIP: {str(e)}")
        return None
    
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        with open(layer_zip, 'rb') as zip_content:
            zip_data = zip_content.read()
            
            if not zip_data or len(zip_data) == 0:
                print(f"⚠️ Error: ZIP file is empty")
                return None
                
            print(f"Uploading layer ZIP ({len(zip_data) / (1024 * 1024):.2f} MB)...")
            
            response = lambda_client.publish_layer_version(
                LayerName=layer_name,
                Description='Dependencies for Perplexity Validator',
                Content={
                    'ZipFile': zip_data
                },
                CompatibleRuntimes=['python3.9']
            )
        
        print(f"Layer published successfully. ARN: {response['LayerVersionArn']}")
        return response['LayerVersionArn']
    except Exception as e:
        print(f"⚠️ Error publishing layer: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def is_package_ready(rebuild_if_older_than_hours=24):
    """Check if the Lambda package already exists and is recent enough."""
    if not OUTPUT_ZIP.exists():
        print(f"Package does not exist: {OUTPUT_ZIP}")
        return False
    
    # Check how old the package is
    file_time = OUTPUT_ZIP.stat().st_mtime
    now = time.time()
    age_hours = (now - file_time) / 3600
    
    if age_hours < rebuild_if_older_than_hours:
        package_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
        print(f"Using existing package (age: {age_hours:.1f} hours, size: {package_size_mb:.2f} MB): {OUTPUT_ZIP}")
        return True
    else:
        print(f"Package is too old ({age_hours:.1f} hours): {OUTPUT_ZIP}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Create and deploy AWS Lambda package')
    parser.add_argument('--deploy', action='store_true', help='Deploy to AWS Lambda after creating package')
    parser.add_argument('--function-name', help='Lambda function name (default: perplexity-validator)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--s3-bucket', default='perplexity-cache', help='S3 bucket for caching (default: perplexity-cache)')
    parser.add_argument('--verify', action='store_true', help='Verify the Lambda function after deployment')
    parser.add_argument('--use-layer', action='store_true', help='Create and use a Lambda layer for dependencies')
    parser.add_argument('--layer-name', help='Custom name for the Lambda layer')
    parser.add_argument('--force-rebuild', action='store_true', help='Force rebuilding the package even if it exists')
    parser.add_argument('--no-rebuild', action='store_true', help='Skip rebuilding the package if it exists')
    parser.add_argument('--run-test', action='store_true', help='Run a test of the function after deployment')
    parser.add_argument('--test-only', action='store_true', help='Only run a test without deploying')
    parser.add_argument('--test-cache', action='store_true', help='Test the caching functionality with multiple calls')
    parser.add_argument('--no-cache-test', action='store_true', help='Skip cache testing in the test run')
    args = parser.parse_args()
    
    # Handle test-only option
    if args.test_only:
        function_name = args.function_name or LAMBDA_CONFIG["FunctionName"]
        print(f"Running test against Lambda function: {function_name}")
        test_lambda_function(function_name, args.region, test_caching=not args.no_cache_test)
        return 0
    
    # Check if we need to build the package
    package_exists = is_package_ready()
    
    if package_exists and not args.force_rebuild:
        if args.no_rebuild:
            print("Skipping package rebuild as requested.")
            build_package = False
        else:
            build_package = not input("Package already exists. Skip rebuilding? (y/N): ").lower().startswith('y')
    else:
        build_package = True
    
    if build_package:
        print("Creating Lambda deployment package...")
        
        try:
            global PACKAGE_DIR  # Make sure we use the global variable
            
            # Create package directory
            PACKAGE_DIR.parent.mkdir(parents=True, exist_ok=True)
            
            # Clean and create package directory
            package_dir = clean_directory(PACKAGE_DIR)
            # Update PACKAGE_DIR if it changed
            PACKAGE_DIR = package_dir
            
            print(f"Using package directory: {PACKAGE_DIR}")
            
            # Install dependencies
            install_dependencies()
            
            # Verify dependencies
            verify_dependencies()
            
            # Copy source files
            copy_source_files(args.use_layer)
            
            # Create ZIP file
            create_zip()
            
            # Get ZIP file size
            size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
            print(f"Done! Package size: {size_mb:.2f} MB")
            print(f"Lambda package created at: {OUTPUT_ZIP}")
        except Exception as e:
            print(f"Error creating Lambda package: {str(e)}")
            import traceback
            traceback.print_exc()
            if not OUTPUT_ZIP.exists():
                print("Failed to create package. Cannot continue with deployment.")
                return 1
    else:
        print(f"Using existing package: {OUTPUT_ZIP}")
        
    # Deploy if requested
    if args.deploy:
        try:
            deploy_to_lambda(
                args.function_name, 
                args.region, 
                args.s3_bucket, 
                args.verify,
                args.use_layer,
                args.layer_name,
                args.run_test
            )
        except Exception as e:
            print(f"Error during deployment: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1
    else:
        print("\nTo deploy to AWS Lambda, use:")
        print(f"python {__file__} --deploy [--use-layer] [--run-test]")
        print("\nTo test an existing Lambda function:")
        print(f"python {__file__} --test-only --function-name perplexity-validator")
        print("\nOr use the AWS Console or AWS CLI:")
        print(f"aws lambda update-function-code --function-name {LAMBDA_CONFIG['FunctionName']} --zip-file fileb://{OUTPUT_ZIP}")
    
    return 0

if __name__ == "__main__":
    main() 