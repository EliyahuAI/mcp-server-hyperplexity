
import os
import logging
import boto3
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Model hierarchy from best to most basic
MODEL_HIERARCHY = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "the-clone-claude", # hybrid perplexity/claude
    "the-clone", # hybrid perplexity/deepseek/claude option
    "deepseek-v3.2",         # Ultra-low cost, most capable DeepSeek
    "deepseek-v3.2-baseten",      # Baseten-hosted DeepSeek V3.2
    "sonar-pro",
    "deepseek-v3.2-exp",     # Ultra-low cost variant with caching
    "deepseek-v3.1",         # Hybrid thinking/non-thinking
    "claude-3-7-sonnet-latest",
    "claude-haiku-4-5",
    "sonar"
]

def get_anthropic_api_key() -> str:
    """Get Anthropic API key from environment or SSM."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if api_key:
        logger.debug("Using Anthropic API key from environment variable")
        return api_key
    
    # Try AWS Systems Manager Parameter Store
    try:
        ssm_client = boto3.client('ssm')
        param_names = ['/Anthropic_API_Key', 'Anthropic_API_Key']
        
        for param_name in param_names:
            try:
                logger.debug(f"Attempting to retrieve Anthropic API key from SSM parameter: {param_name}")
                response = ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                logger.debug(f"Successfully retrieved Anthropic API key from {param_name}")
                return response['Parameter']['Value']
            except Exception as e:
                logger.warning(f"Failed to get Anthropic API key from SSM parameter '{param_name}': {str(e)}")
                continue
        
        logger.error("Failed to retrieve Anthropic API key from any SSM parameter variant")
        raise Exception(f"Anthropic API key not found in SSM. Tried parameters: {param_names}")
        
    except Exception as e:
        logger.error(f"Failed to retrieve Anthropic API key: {str(e)}")
        raise

def get_baseten_api_key() -> str:
    """Get Baseten API key from environment or SSM."""
    api_key = os.environ.get('BASETEN_API_KEY')
    if api_key:
        logger.debug("Using Baseten API key from environment variable")
        return api_key
    
    # Try AWS Systems Manager Parameter Store
    try:
        ssm_client = boto3.client('ssm')
        param_names = ['/perplexity-validator/baseten-credentials', 'Baseten_API_Key']
        
        for param_name in param_names:
            try:
                logger.debug(f"Attempting to retrieve Baseten API key from SSM parameter: {param_name}")
                response = ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                logger.debug(f"Successfully retrieved Baseten API key from {param_name}")
                return response['Parameter']['Value']
            except Exception as e:
                logger.warning(f"Failed to get Baseten API key from SSM parameter '{param_name}': {str(e)}")
                continue
        
        # If we get here, all parameter names failed
        raise Exception("Could not retrieve Baseten API key from any SSM parameter")
    except Exception as e:
        logger.error(f"Failed to retrieve Baseten API key: {str(e)}")
        raise

def get_perplexity_api_key() -> str:
    """Get Perplexity API key from environment or SSM."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if api_key:
        logger.debug("Using Perplexity API key from environment variable")
        return api_key
    
    # Try AWS Systems Manager Parameter Store
    try:
        ssm_client = boto3.client('ssm')
        param_names = ['/perplexity-validator/perplexity-api-key', 'Perplexity_API_Key']
        
        for param_name in param_names:
            try:
                logger.debug(f"Attempting to retrieve Perplexity API key from SSM parameter: {param_name}")
                response = ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                logger.debug(f"Successfully retrieved Perplexity API key from {param_name}")
                return response['Parameter']['Value']
            except Exception as e:
                logger.warning(f"Failed to get Perplexity API key from SSM parameter '{param_name}': {str(e)}")
                continue
        
        # If we get here, all parameter names failed
        raise Exception("Could not retrieve Perplexity API key from any SSM parameter")
    except Exception as e:
        logger.error(f"Failed to retrieve Perplexity API key: {str(e)}")
        raise

def get_vertex_credentials_from_ssm() -> Optional[str]:
    """Get Google Cloud service account JSON from SSM Parameter Store."""
    # Try AWS Systems Manager Parameter Store
    try:
        ssm_client = boto3.client('ssm')
        # Try parameter names in order (first one uses existing wildcard permissions)
        param_names = [
            '/perplexity-validator/vertex-credentials',  # Matches existing wildcard permission
            'perplexity-validator/vertex-credentials',   # Without leading slash (user's format)
            '/Vertex_Credentials',
            'Vertex_Credentials',
            'GOOGLE_APPLICATION_CREDENTIALS'
        ]

        for param_name in param_names:
            try:
                logger.debug(f"Attempting to retrieve Vertex credentials from SSM parameter: {param_name}")
                response = ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                credentials_json = response['Parameter']['Value']
                logger.debug(f"Successfully retrieved Vertex credentials from {param_name}")
                return credentials_json
            except Exception as e:
                logger.warning(f"Failed to get Vertex credentials from SSM parameter '{param_name}': {str(e)}")
                continue

        # If we get here, all parameter names failed
        logger.warning("Could not retrieve Vertex credentials from any SSM parameter")
        return None
    except Exception as e:
        logger.warning(f"Failed to retrieve Vertex credentials: {str(e)}")
        return None

def setup_vertex_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    Setup Vertex AI credentials from environment or SSM.
    Returns (project_id, location).
    """
    try:
        # Hardcoded project ID (as requested by user)
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0650358146')
        location = os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-west2')  # us-west2 supports DeepSeek MaaS

        # Set up credentials from SSM Parameter Store if not in environment
        if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            vertex_creds_json = get_vertex_credentials_from_ssm()
            if vertex_creds_json:
                # Write credentials to temp file for google-auth library
                temp_creds_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                temp_creds_file.write(vertex_creds_json)
                temp_creds_file.flush()
                temp_creds_file.close()
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_creds_file.name
                logger.debug(f"AI_API_CLIENT: Vertex credentials loaded from SSM to temp file")

        logger.debug(f"AI_API_CLIENT: Vertex AI initialized (lightweight mode, project={project_id}, location={location})")
        return project_id, location

    except Exception as e:
        logger.warning(f"AI_API_CLIENT: Failed to initialize Vertex AI: {e}")
        return None, None
