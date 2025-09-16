#!/usr/bin/env python
"""
Environment Configuration Helper Module

This module provides utilities for managing environment-specific configurations
for deployment scripts. It supports dev, test, staging, and prod environments.
"""
import json
import os
from pathlib import Path
from typing import Dict, Any

def load_environment_config(environment: str = "prod") -> Dict[str, Any]:
    """
    Load environment-specific configuration from environments.json
    
    Args:
        environment: Environment name (dev, test, staging, prod)
        
    Returns:
        Dictionary containing environment-specific configuration
        
    Raises:
        ValueError: If environment is not found in configuration
        FileNotFoundError: If environments.json is not found
    """
    script_dir = Path(__file__).parent
    config_file = script_dir / "environments.json"
    
    if not config_file.exists():
        raise FileNotFoundError(f"Environment configuration file not found: {config_file}")
    
    with open(config_file, 'r') as f:
        all_configs = json.load(f)
    
    if environment not in all_configs:
        available_envs = list(all_configs.keys())
        raise ValueError(f"Environment '{environment}' not found. Available environments: {available_envs}")
    
    return all_configs[environment]

def apply_environment_to_lambda_config(base_config: Dict[str, Any], environment: str = "prod") -> Dict[str, Any]:
    """
    Apply environment-specific modifications to a Lambda configuration
    
    Args:
        base_config: Base Lambda configuration dictionary
        environment: Environment name (dev, test, staging, prod)
        
    Returns:
        Modified Lambda configuration with environment-specific values
    """
    env_config = load_environment_config(environment)
    config = base_config.copy()
    
    # Apply resource suffix to function name
    original_name = config.get("FunctionName", "")
    config["FunctionName"] = original_name + env_config["resource_suffix"]
    
    # Update environment variables
    if "Environment" not in config:
        config["Environment"] = {"Variables": {}}
    if "Variables" not in config["Environment"]:
        config["Environment"]["Variables"] = {}
    
    # Apply environment-specific S3 bucket names
    config["Environment"]["Variables"]["S3_UNIFIED_BUCKET"] = env_config["s3_unified_bucket"]
    config["Environment"]["Variables"]["S3_DOWNLOAD_BUCKET"] = env_config["s3_download_bucket"]
    
    # Add environment tag for identification
    config["Environment"]["Variables"]["DEPLOYMENT_ENVIRONMENT"] = environment
    config["Environment"]["Variables"]["ENVIRONMENT_TAG"] = env_config["environment_tag"]
    
    return config

def get_api_gateway_urls(environment: str = "prod") -> Dict[str, str]:
    """
    Get API Gateway URLs for the specified environment
    
    Args:
        environment: Environment name (dev, test, staging, prod)
        
    Returns:
        Dictionary containing API Gateway URLs for the environment
    """
    env_config = load_environment_config(environment)
    
    # Base API Gateway IDs (these would need to be updated with actual values)
    # For now, using placeholder logic - in practice, you'd have different gateway IDs per environment
    if environment == "dev":
        rest_api_id = "dev-api-id"  # Replace with actual dev API Gateway ID
        websocket_api_id = "dev-ws-id"  # Replace with actual dev WebSocket API ID
    elif environment == "test":
        rest_api_id = "test-api-id"  # Replace with actual test API Gateway ID
        websocket_api_id = "test-ws-id"  # Replace with actual test WebSocket API ID
    elif environment == "staging":
        rest_api_id = "staging-api-id"  # Replace with actual staging API Gateway ID
        websocket_api_id = "staging-ws-id"  # Replace with actual staging WebSocket API ID
    else:  # prod
        rest_api_id = "a0tk95o95g"  # Current production REST API ID
        websocket_api_id = "xt6790qk9f"  # Current production WebSocket API ID
    
    stage = env_config["api_gateway_stage"]
    
    return {
        "rest_api_url": f"https://{rest_api_id}.execute-api.us-east-1.amazonaws.com/{stage}",
        "websocket_url": f"wss://{websocket_api_id}.execute-api.us-east-1.amazonaws.com/{stage}"
    }

def print_environment_info(environment: str):
    """
    Print environment configuration information for debugging
    
    Args:
        environment: Environment name to display info for
    """
    try:
        env_config = load_environment_config(environment)
        print(f"[INFO] Environment: {environment}")
        print(f"[INFO] Resource suffix: {env_config['resource_suffix']}")
        print(f"[INFO] S3 unified bucket: {env_config['s3_unified_bucket']}")
        print(f"[INFO] S3 download bucket: {env_config['s3_download_bucket']}")
        print(f"[INFO] API Gateway stage: {env_config['api_gateway_stage']}")
        
        api_urls = get_api_gateway_urls(environment)
        print(f"[INFO] REST API URL: {api_urls['rest_api_url']}")
        print(f"[INFO] WebSocket URL: {api_urls['websocket_url']}")
        
    except Exception as e:
        print(f"[ERROR] Failed to load environment config: {e}")

if __name__ == "__main__":
    # Test the module
    import sys
    
    if len(sys.argv) > 1:
        env = sys.argv[1]
    else:
        env = "prod"
    
    print_environment_info(env)