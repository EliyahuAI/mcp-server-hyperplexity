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
    
    # Update legacy S3 bucket variables to use unified bucket (for backward compatibility)
    if "S3_RESULTS_BUCKET" in config["Environment"]["Variables"]:
        config["Environment"]["Variables"]["S3_RESULTS_BUCKET"] = env_config["s3_unified_bucket"]
    if "S3_CACHE_BUCKET" in config["Environment"]["Variables"]:
        # Use shared production cache bucket for all environments (cache is shared for efficiency)
        config["Environment"]["Variables"]["S3_CACHE_BUCKET"] = "hyperplexity-storage"
    if "S3_CONFIG_BUCKET" in config["Environment"]["Variables"]:
        config["Environment"]["Variables"]["S3_CONFIG_BUCKET"] = env_config["s3_download_bucket"]
    
    # Apply environment-specific validator lambda name (for interface lambda)
    if "VALIDATOR_LAMBDA_NAME" in config["Environment"]["Variables"]:
        base_validator_name = config["Environment"]["Variables"]["VALIDATOR_LAMBDA_NAME"]
        config["Environment"]["Variables"]["VALIDATOR_LAMBDA_NAME"] = base_validator_name + env_config["resource_suffix"]
    
    # Apply environment-specific config lambda name (for interface lambda)
    if "CONFIG_LAMBDA_NAME" in config["Environment"]["Variables"]:
        base_config_name = config["Environment"]["Variables"]["CONFIG_LAMBDA_NAME"]
        config["Environment"]["Variables"]["CONFIG_LAMBDA_NAME"] = base_config_name + env_config["resource_suffix"]
    
    # Keep WebSocket URL pointing to /prod stage (shared WebSocket infrastructure)
    if "WEBSOCKET_API_URL" in config["Environment"]["Variables"]:
        base_ws_url = config["Environment"]["Variables"]["WEBSOCKET_API_URL"]
        # Ensure all environments use /prod stage for shared WebSocket infrastructure
        if "/dev" in base_ws_url:
            config["Environment"]["Variables"]["WEBSOCKET_API_URL"] = base_ws_url.replace("/dev", "/prod")
        elif "/test" in base_ws_url:
            config["Environment"]["Variables"]["WEBSOCKET_API_URL"] = base_ws_url.replace("/test", "/prod")
        elif "/staging" in base_ws_url:
            config["Environment"]["Variables"]["WEBSOCKET_API_URL"] = base_ws_url.replace("/staging", "/prod")
        # /prod stays as /prod
    
    # Add environment tag for identification
    config["Environment"]["Variables"]["DEPLOYMENT_ENVIRONMENT"] = environment
    config["Environment"]["Variables"]["ENVIRONMENT_TAG"] = env_config["environment_tag"]
    
    return config

def apply_environment_to_api_gateway_config(base_config: Dict[str, Any], environment: str = "prod") -> Dict[str, Any]:
    """
    Apply environment-specific modifications to an API Gateway configuration
    
    Args:
        base_config: Base API Gateway configuration dictionary
        environment: Environment name (dev, test, staging, prod)
        
    Returns:
        Modified API Gateway configuration with environment-specific values
    """
    env_config = load_environment_config(environment)
    config = base_config.copy()
    
    # Apply resource suffix to API name
    original_name = config.get("ApiName", "")
    config["ApiName"] = original_name + env_config["resource_suffix"]
    
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
    
    # For now, return placeholder URLs that will be updated after deployment
    # The actual URLs will be determined after the API Gateway is created
    # These placeholders help with documentation and testing
    if environment == "prod":
        rest_api_id = "a0tk95o95g"  # Current production REST API ID
        websocket_api_id = "xt6790qk9f"  # Current production WebSocket API ID
    else:
        # Placeholder IDs - will be replaced with actual values after deployment
        rest_api_id = f"{environment}-api-placeholder"
        websocket_api_id = f"{environment}-ws-placeholder"
    
    stage = env_config["api_gateway_stage"]
    
    return {
        "rest_api_url": f"https://{rest_api_id}.execute-api.us-east-1.amazonaws.com/{stage}",
        "websocket_url": f"wss://{websocket_api_id}.execute-api.us-east-1.amazonaws.com/{stage}"
    }

def update_frontend_with_api_urls(environment: str, rest_api_id: str, websocket_api_id: str = None) -> str:
    """
    Generate frontend configuration snippet with actual API Gateway URLs
    
    Args:
        environment: Environment name (dev, test, staging, prod)
        rest_api_id: Actual REST API Gateway ID
        websocket_api_id: Actual WebSocket API Gateway ID (optional)
        
    Returns:
        JavaScript configuration snippet to update frontend
    """
    env_config = load_environment_config(environment)
    stage = env_config["api_gateway_stage"]
    
    rest_url = f"https://{rest_api_id}.execute-api.us-east-1.amazonaws.com/{stage}"
    ws_url = f"wss://{websocket_api_id or 'xt6790qk9f'}.execute-api.us-east-1.amazonaws.com/{stage}"
    
    return f"""
// Update frontend configuration for {environment} environment:
// Replace in ENV_CONFIGS.{environment}:
apiBase: '{rest_url}',
websocketUrl: '{ws_url}',
"""

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