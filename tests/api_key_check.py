"""
Test script to verify which Perplexity API key is being used.
"""
import os
import sys
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("api_key_check")

# Add the src directory to path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from lambda_function import get_perplexity_api_key

def main():
    """Check which API key is being used."""
    logger.info("Checking Perplexity API key...")
    
    # Check for environment variable
    env_key = os.environ.get('PERPLEXITY_API_KEY')
    if env_key:
        masked_key = f"{env_key[:4]}...{env_key[-4:]}" if len(env_key) > 8 else "***masked***"
        logger.info(f"Found PERPLEXITY_API_KEY in environment: {masked_key}")
    else:
        logger.info("No PERPLEXITY_API_KEY found in environment")
    
    # Try to get the key using the function
    try:
        api_key = get_perplexity_api_key()
        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***masked***"
        logger.info(f"API key from get_perplexity_api_key(): {masked_key}")
        logger.info("✅ Successfully retrieved an API key!")
        
        # Check if it's the fallback key
        fallback = "pp-..."  # This should match what you put in lambda_function.py
        if api_key == fallback:
            logger.warning("⚠️ Using FALLBACK test key!")
        else:
            logger.info("Using a real API key (not the fallback)")
            
    except Exception as e:
        logger.error(f"Error getting API key: {str(e)}")

if __name__ == "__main__":
    # Set TEST_MODE to enable fallback
    os.environ['TEST_MODE'] = 'true'
    main() 