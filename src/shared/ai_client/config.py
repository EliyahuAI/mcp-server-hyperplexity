
import os
import logging
import boto3
import tempfile
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# =============================================================================
# Model Timeout Configuration
# =============================================================================
# Timeouts in seconds for different model tiers
# These can be overridden via environment variables or at runtime

TIMEOUT_FAST = 60      # Fast models: Haiku, Gemini 2.0 Flash
TIMEOUT_MEDIUM = 240   # Medium models: Sonar, Sonar Pro (4 mins)
TIMEOUT_SLOW = 300     # Slow models: DeepSeek, Anthropic, Gemini 2.5 (5 mins)
TIMEOUT_DEFAULT = 300  # Default timeout for unknown models

# Model-specific timeout mapping
# Models not listed here will use TIMEOUT_DEFAULT
MODEL_TIMEOUTS: Dict[str, int] = {
    # Fast models (60s)
    'claude-haiku-4-5': TIMEOUT_FAST,
    'claude-3-5-haiku-20241022': TIMEOUT_FAST,
    'gemini-2.5-flash-lite': TIMEOUT_FAST,
    'gemini-2.5-flash-lite-exp': TIMEOUT_FAST,

    # Medium models (4 mins)
    'sonar': TIMEOUT_MEDIUM,
    'sonar-pro': TIMEOUT_MEDIUM,
    'sonar-reasoning': TIMEOUT_MEDIUM,

    # Slow models (5 mins) - explicitly listed for clarity
    'deepseek-v3.2': TIMEOUT_SLOW,
    'deepseek-v3.2-baseten': TIMEOUT_SLOW,
    'claude-sonnet-4-6': TIMEOUT_SLOW,
    'claude-3-5-sonnet-20241022': TIMEOUT_SLOW,
    'claude-opus-4-6': TIMEOUT_SLOW,
    'gemini-2.5-flash': TIMEOUT_SLOW,
    'gemini-1.5-pro': TIMEOUT_SLOW,
    # Gemini 3 Flash Preview (thinking model — needs extra time for reasoning)
    'gemini-3-flash-preview': TIMEOUT_SLOW,
    'gemini-3-flash-preview-low': TIMEOUT_SLOW,
    'gemini-3-flash-preview-high': TIMEOUT_SLOW,
    'gemini-3-flash-preview-min': TIMEOUT_SLOW,
}

def get_model_timeout(model: str, override: Optional[int] = None) -> int:
    """
    Get the timeout for a specific model.

    Args:
        model: Model name/identifier
        override: Optional timeout override (takes precedence)

    Returns:
        Timeout in seconds
    """
    # Check for override
    if override is not None:
        return override

    # Check environment variable override (AI_CLIENT_TIMEOUT_<MODEL>)
    env_key = f"AI_CLIENT_TIMEOUT_{model.upper().replace('-', '_').replace('.', '_')}"
    env_timeout = os.environ.get(env_key)
    if env_timeout:
        try:
            return int(env_timeout)
        except ValueError:
            logger.warning(f"Invalid timeout in {env_key}: {env_timeout}, using default")

    # Check global environment override
    global_override = os.environ.get('AI_CLIENT_TIMEOUT_DEFAULT')
    if global_override:
        try:
            return int(global_override)
        except ValueError:
            pass

    # Look up model-specific timeout
    # Try exact match first
    if model in MODEL_TIMEOUTS:
        return MODEL_TIMEOUTS[model]

    # Try partial match (for model variants)
    model_lower = model.lower()
    for known_model, timeout in MODEL_TIMEOUTS.items():
        if known_model.lower() in model_lower or model_lower in known_model.lower():
            return timeout

    # Default timeout
    return TIMEOUT_DEFAULT


def get_timeout_tier(model: str) -> str:
    """Get human-readable timeout tier for logging."""
    timeout = get_model_timeout(model)
    if timeout <= TIMEOUT_FAST:
        return f"fast ({timeout}s)"
    elif timeout <= TIMEOUT_MEDIUM:
        return f"medium ({timeout}s)"
    else:
        return f"slow ({timeout}s)"


# Per-model backup chains, organized by capability stack.
#
# Models within the same stack have compatible capabilities — they access the same
# types of information and produce results of the same quality class.
# Cross-stack backups are avoided because:
#   - Web-native → non-web: loses real-time data, results degrade silently
#   - Non-web → web-native: overkill cost, wrong tool for the task
#
# STACK 1 — WEB SEARCH NATIVE  (sonar, the-clone — real-time internet access)
# STACK 2 — THINKING / REASONING  (gemini-3-flash-preview, claude, deepseek)
# STACK 3 — EXTRACTION / COST-OPTIMIZED  (gemini-2.5-flash-lite, haiku, minimax)
#
MODEL_BACKUPS: Dict[str, List[str]] = {

    # ── STACK 1: Web Search Native ───────────────────────────────────────────
    # Sonar family (Perplexity — real-time grounded search)
    "sonar-pro":           ["sonar"],                        # step down within web stack
    "sonar":               ["sonar-pro"],                    # step up within web stack
    "sonar-reasoning-pro": ["sonar-pro", "sonar"],

    # The Clone family (Perplexity + DeepSeek/Claude synthesis hybrid)
    "the-clone":         ["the-clone-baseten", "the-clone-claude"],
    "the-clone-baseten": ["the-clone", "the-clone-claude"],
    "the-clone-claude":  ["the-clone", "the-clone-baseten"],
    "the-clone-kimi":    ["the-clone", "the-clone-baseten"],

    # ── STACK 2: Thinking / Reasoning ────────────────────────────────────────
    # Gemini 3 Flash Preview — HIGH thinking (config-gen, column-def, upload interview)
    "gemini-3-flash-preview-high":            ["openrouter/gemini-3-flash-preview-high", "claude-sonnet-4-6"],
    "openrouter/gemini-3-flash-preview-high": ["gemini-3-flash-preview-high", "claude-sonnet-4-6"],

    # Gemini 3 Flash Preview — MEDIUM thinking (routing, initial decision)
    "gemini-3-flash-preview":            ["openrouter/gemini-3-flash-preview", "claude-sonnet-4-6"],
    "openrouter/gemini-3-flash-preview": ["gemini-3-flash-preview", "claude-sonnet-4-6"],

    # Gemini 3 Flash Preview — LOW thinking (light reasoning)
    "gemini-3-flash-preview-low":            ["openrouter/gemini-3-flash-preview-low", "gemini-3-flash-preview"],
    "openrouter/gemini-3-flash-preview-low": ["gemini-3-flash-preview-low", "gemini-3-flash-preview"],

    # Gemini 3 Flash Preview — MIN thinking (fast inference, no thinking budget)
    # Closest peers are extraction-stack models at similar cost/speed
    "gemini-3-flash-preview-min":            ["openrouter/gemini-3-flash-preview-min", "gemini-2.5-flash-lite"],
    "openrouter/gemini-3-flash-preview-min": ["gemini-3-flash-preview-min", "gemini-2.5-flash-lite"],

    # Claude — strong reasoning
    "claude-opus-4-6":   ["claude-sonnet-4-6", "gemini-3-flash-preview-high"],
    "claude-sonnet-4-6": ["gemini-3-flash-preview-high", "claude-opus-4-6"],

    # DeepSeek — cheap synthesis (Vertex primary, Baseten backup)
    "deepseek-v3.2":         ["deepseek-v3.2-baseten", "claude-haiku-4-5"],
    "deepseek-v3.2-baseten": ["deepseek-v3.2", "claude-haiku-4-5"],
    "deepseek-v3.2-exp":     ["deepseek-v3.2", "deepseek-v3.2-baseten"],

    # ── STACK 3: Extraction / Cost-Optimized ─────────────────────────────────
    # Gemini 2.5 Flash Lite (primary extraction model — fast and cheap)
    "gemini-2.5-flash-lite":            ["openrouter/gemini-2.5-flash-lite", "deepseek-v3.2"],
    "openrouter/gemini-2.5-flash-lite": ["gemini-2.5-flash-lite", "deepseek-v3.2"],

    # Gemini 2.5 Flash (superseded; redirect to Gemini 3 for reasoning tasks)
    "gemini-2.5-flash":            ["gemini-3-flash-preview", "openrouter/gemini-3-flash-preview"],
    "openrouter/gemini-2.5-flash": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],

    # Claude Haiku — cheapest Claude, good for classification and light tasks
    "claude-haiku-4-5": ["gemini-2.5-flash-lite", "deepseek-v3.2"],

    # OpenRouter models
    "minimax/minimax-m2.5": ["gemini-2.5-flash-lite", "deepseek-v3.2"],
    "moonshotai/kimi-k2.5": ["claude-sonnet-4-6", "deepseek-v3.2"],
}

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

def get_openrouter_api_key() -> Optional[str]:
    """Get OpenRouter API key from environment or SSM."""
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if api_key:
        logger.debug("Using OpenRouter API key from environment variable")
        return api_key

    try:
        ssm_client = boto3.client('ssm')
        param_names = [
            '/perplexity-validator/OPENROUTER_API_KEY',
            '/perplexity-validator/openrouter-api-key',
            'OpenRouter_API_Key',
        ]
        for param_name in param_names:
            try:
                response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
                logger.debug(f"Retrieved OpenRouter API key from SSM {param_name}")
                return response['Parameter']['Value']
            except Exception as e:
                logger.warning(f"Failed to get OpenRouter API key from SSM '{param_name}': {e}")
                continue
        logger.warning("OpenRouter API key not found in environment or SSM")
        return None
    except Exception as e:
        logger.warning(f"Failed to retrieve OpenRouter API key: {e}")
        return None


def get_google_ai_studio_api_key() -> Optional[str]:
    """Get Google AI Studio API key from environment or SSM."""
    api_key = os.environ.get('GOOGLE_AI_STUDIO_API_KEY')
    if api_key:
        logger.debug("Using Google AI Studio API key from environment variable")
        return api_key

    # Try AWS Systems Manager Parameter Store
    try:
        ssm_client = boto3.client('ssm')
        param_names = [
            '/perplexity-validator/Google_AI_studio_API_key',
            '/perplexity-validator/google-ai-studio-api-key',
            'Google_AI_Studio_API_Key'
        ]

        for param_name in param_names:
            try:
                logger.debug(f"Attempting to retrieve Google AI Studio API key from SSM parameter: {param_name}")
                response = ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                logger.debug(f"Successfully retrieved Google AI Studio API key from {param_name}")
                return response['Parameter']['Value']
            except Exception as e:
                logger.warning(f"Failed to get Google AI Studio API key from SSM parameter '{param_name}': {str(e)}")
                continue

        # If we get here, all parameter names failed
        logger.warning("Could not retrieve Google AI Studio API key from any SSM parameter")
        return None
    except Exception as e:
        logger.warning(f"Failed to retrieve Google AI Studio API key: {str(e)}")
        return None


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
        # Force correct project (temp fix for env var caching issue)
        project_id = 'gen-lang-client-0650358146'
        location = os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1')  # us-central1 for Gemini

        # Strip quotes if present (common issue with env vars)
        location = location.strip('"').strip("'") if location else 'us-central1'

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
