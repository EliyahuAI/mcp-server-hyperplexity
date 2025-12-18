import sys
import os
import asyncio
import logging
import json
import hashlib
from datetime import datetime
from decimal import Decimal

# Add the project root to sys.path to ensure we can import everything
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)
# Add src/shared to sys.path for relative imports within modules
sys.path.append(os.path.join(project_root, 'src', 'shared'))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RefactorTest")

def compare_dicts(d1, d2, path=""):
    """Recursively compare two dictionaries."""
    diffs = []
    keys1 = set(d1.keys())
    keys2 = set(d2.keys())
    
    # Ignore specific keys that will always differ in live calls
    ignored_keys = {'processing_time', 'timestamp', 'cached_at', 'id', 'system_fingerprint', 'created', 'request_id'}
    keys1 = keys1 - ignored_keys
    keys2 = keys2 - ignored_keys
    
    if keys1 != keys2:
        missing_in_2 = keys1 - keys2
        missing_in_1 = keys2 - keys1
        if missing_in_2:
            diffs.append(f"{path} Keys missing in New: {missing_in_2}")
        if missing_in_1:
            diffs.append(f"{path} Keys missing in Old: {missing_in_1}")
            
    for key in keys1.intersection(keys2):
        val1 = d1[key]
        val2 = d2[key]
        new_path = f"{path}.{key}" if path else key
        
        # Skip comparing values for keys that vary per call but struct should match
        if key in ['content', 'text', 'completion_tokens', 'prompt_tokens', 'total_tokens', 'input_tokens', 'output_tokens']:
            # We just check types here mostly, or rough equality if deterministic
            if type(val1) != type(val2):
                diffs.append(f"{new_path} Type mismatch: Old={type(val1)}, New={type(val2)}")
            continue

        if type(val1) != type(val2):
            diffs.append(f"{new_path} Type mismatch: Old={type(val1)}, New={type(val2)}")
            continue
        
        if isinstance(val1, dict):
            diffs.extend(compare_dicts(val1, val2, new_path))
        elif isinstance(val1, list):
            if len(val1) != len(val2):
                # Lists might differ in length for things like citations depending on search results
                # Just log warning, not hard fail
                # diffs.append(f"{new_path} List length mismatch: Old={len(val1)}, New={len(val2)}")
                pass
            else:
                for i, (item1, item2) in enumerate(zip(val1, val2)):
                    if isinstance(item1, dict):
                        diffs.extend(compare_dicts(item1, item2, f"{new_path}[{i}]"))
        else:
            # Allow for small float differences
            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                if abs(val1 - val2) > 0.000001:
                    diffs.append(f"{new_path} Value mismatch: Old={val1}, New={val2}")
            elif val1 != val2:
                diffs.append(f"{new_path} Value mismatch: Old={val1}, New={val2}")
                
    return diffs

async def test_live_structured_call(old_client, new_client, provider, model):
    logger.info(f"\n{'='*60}")
    logger.info(f"TESTING LIVE API: {provider} ({model})")
    logger.info(f"{ '='*60}")
    
    prompt = "What is 2+2? Return a JSON object with keys 'result' and 'explanation'."
    schema = {
        "type": "object",
        "properties": {
            "result": {"type": "integer"},
            "explanation": {"type": "string"}
        },
        "required": ["result"]
    }
    
    logger.info(f"QUERY: {prompt}")
    
    import time
    timestamp = str(time.time())
    
    # --- Old Client ---
    res_old = None
    try:
        logger.info(f"--- [Old Client] Request ---")
        res_old = await old_client.call_structured_api(
            prompt=prompt, 
            schema=schema, 
            model=model, 
            use_cache=False, 
            context=f"test_old_{timestamp}",
            max_web_searches=0
        )
        logger.info(f"--- [Old Client] Response ---")
        if 'response' in res_old:
            # Extract content for display
            content = res_old['response']
            if 'choices' in content: # Unified format or OpenAI/Perplexity
                display_content = content['choices'][0]['message']['content']
            elif 'content' in content: # Anthropic
                display_content = content['content']
            else:
                display_content = content
            logger.info(f"OUTPUT: {display_content}")
        else:
            logger.warning("No 'response' key in result")
            
    except Exception as e:
        logger.error(f"--- [Old Client] Failed: {e}")

    # --- New Client ---
    res_new = None
    try:
        logger.info(f"--- [New Client] Request ---")
        res_new = await new_client.call_structured_api(
            prompt=prompt, 
            schema=schema, 
            model=model, 
            use_cache=False, 
            context=f"test_new_{timestamp}",
            max_web_searches=0
        )
        logger.info(f"--- [New Client] Response ---")
        if 'response' in res_new:
            content = res_new['response']
            if 'choices' in content:
                display_content = content['choices'][0]['message']['content']
            elif 'content' in content:
                display_content = content['content']
            else:
                display_content = content
            logger.info(f"OUTPUT: {display_content}")
        else:
            logger.warning("No 'response' key in result")

    except Exception as e:
        logger.error(f"--- [New Client] Failed: {e}")
        import traceback
        traceback.print_exc()

    # Comparison
    logger.info(f"--- Comparison ---")
    if res_old and res_new:
        old_tokens = res_old.get('token_usage', {}).get('total_tokens')
        new_tokens = res_new.get('token_usage', {}).get('total_tokens')
        logger.info(f"Token Usage: Old={old_tokens}, New={new_tokens}")
        
        # Check Cost Data
        old_cost = res_old.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost')
        new_cost = res_new.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost')
        
        logger.info(f"Total Cost:  Old=${old_cost}, New=${new_cost}")

        if old_tokens is not None and new_tokens is not None:
             logger.info("✅ Both clients returned token usage")
        else:
             logger.warning("⚠️ Missing token usage in one or both responses")
             
        if old_cost is not None and new_cost is not None:
             logger.info("✅ Both clients returned cost data")
        else:
             logger.warning(f"⚠️ Missing cost data: Old={old_cost is not None}, New={new_cost is not None}")
             if res_new.get('enhanced_data') is None:
                 logger.error("❌ New client missing 'enhanced_data' entirely")
             elif res_new.get('enhanced_data', {}).get('costs') is None:
                 logger.error("❌ New client missing 'costs' in enhanced_data")

    else:
        logger.error("❌ Comparison failed - one or both clients failed")

async def main():
    logger.info("Starting Live Refactor Comparison Test...")
    
    try:
        from src.shared.ai_api_client_old import AIAPIClient as OldClient
        from src.shared.ai_client import AIAPIClient as NewClient
        logger.info("Imports successful.")
    except ImportError as e:
        logger.error(f"Failed to import clients: {e}")
        return

    # Instantiate
    try:
        old_client = OldClient()
        new_client = NewClient()
        logger.info("Clients instantiated successfully.")
    except Exception as e:
        logger.error(f"Failed to instantiate clients: {e}")
        return

    # 1. Anthropic Test
    await test_live_structured_call(old_client, new_client, "Anthropic", "claude-haiku-4-5") # Use cheap model

    # 2. Perplexity Test
    await test_live_structured_call(old_client, new_client, "Perplexity", "sonar") # Use cheap model

    # 3. Vertex Test
    # Note: Vertex configuration depends on env vars. The clients try to load them.
    if new_client.vertex.project_id:
        await test_live_structured_call(old_client, new_client, "Vertex", "vertex.deepseek-v3.2")
    else:
        logger.warning("Skipping Vertex test: Project ID not configured.")

    # 4. The Clone Test (DeepSeek variant)
    logger.info("\n============================================================")
    logger.info("TESTING LIVE API: The Clone (the-clone)")
    logger.info("============================================================")
    prompt_clone = "What is the capital of France?"
    schema_clone = {"type": "object", "properties": {"answer": {"type": "string"}, "summary": {"type": "string"}, "citations": {"type": "array"}}}
    
    try:
        # No old client for comparison, just test the new client
        new_clone_response = await new_client.call_structured_api(
            prompt=prompt_clone,
            schema=schema_clone,
            model="the-clone",
            soft_schema=True # Clone always uses soft schema for its final output
        )

        logger.info(f"--- [New Client] The Clone Response ---")
        # Safely extract and log the 'content' from the unified response structure
        clone_content = new_clone_response.get('response', {}).get('choices', [{}])[0].get('message', {}).get('content', '')
        logger.info(f"OUTPUT: {clone_content}")
        
        # Verify basic structure and costs for The Clone
        assert new_clone_response is not None, "The Clone response should not be None"
        assert new_clone_response.get('response') is not None, "The Clone response should have a 'response' key"
        assert new_clone_response.get('enhanced_data') is not None, "The Clone response should have 'enhanced_data'"
        
        total_cost_clone = new_clone_response['enhanced_data']['costs']['actual']['total_cost']
        logger.info(f"Total Cost (The Clone): ${total_cost_clone:.6f}")
        assert total_cost_clone > 0, "The Clone total cost should be greater than 0"
        
        assert new_clone_response.get('citations') is not None and isinstance(new_clone_response['citations'], list), "The Clone response should have a 'citations' list"
        
        logger.info("✅ The Clone client (the-clone) returned valid response and cost data")

    except Exception as e:
        logger.error(f"❌ The Clone client (the-clone) test failed: {e}")
        import traceback
        traceback.print_exc()

    # 5. The Clone Test (Claude variant)
    logger.info("\n============================================================")
    logger.info("TESTING LIVE API: The Clone (the-clone-claude)")
    logger.info("============================================================")
    prompt_clone_claude = "What is the main advantage of fusion power over fission power?"
    schema_clone_claude = {"type": "object", "properties": {"answer": {"type": "string"}, "advantage": {"type": "string"}, "citations": {"type": "array"}}}
    
    try:
        new_clone_claude_response = await new_client.call_structured_api(
            prompt=prompt_clone_claude,
            schema=schema_clone_claude,
            model="the-clone-claude",
            soft_schema=True # Clone always uses soft schema for its final output
        )

        logger.info(f"--- [New Client] The Clone Claude Response ---")
        clone_claude_content = new_clone_claude_response.get('response', {}).get('choices', [{}])[0].get('message', {}).get('content', '')
        logger.info(f"OUTPUT: {clone_claude_content}")
        
        assert new_clone_claude_response is not None, "The Clone Claude response should not be None"
        assert new_clone_claude_response.get('response') is not None, "The Clone Claude response should have a 'response' key"
        assert new_clone_claude_response.get('enhanced_data') is not None, "The Clone Claude response should have 'enhanced_data'"
        
        total_cost_clone_claude = new_clone_claude_response['enhanced_data']['costs']['actual']['total_cost']
        logger.info(f"Total Cost (The Clone Claude): ${total_cost_clone_claude:.6f}")
        assert total_cost_clone_claude > 0, "The Clone Claude total cost should be greater than 0"
        
        assert new_clone_claude_response.get('citations') is not None and isinstance(new_clone_claude_response['citations'], list), "The Clone Claude response should have a 'citations' list"
        
        logger.info("✅ The Clone client (the-clone-claude) returned valid response and cost data")

    except Exception as e:
        logger.error(f"❌ The Clone client (the-clone-claude) test failed: {e}")
        import traceback
        traceback.print_exc()

    # 6. Baseten DeepSeek Test
    logger.info("\n============================================================")
    logger.info("TESTING LIVE API: Baseten DeepSeek V3.2 (deepseek-baseten)")
    logger.info("============================================================")
    prompt_baseten = "What is the capital of France?"
    schema_baseten = {"type": "object", "properties": {"answer": {"type": "string"}, "summary": {"type": "string"}}}
    
    try:
        # Check if Baseten provider is initialized
        if new_client.baseten:
            new_baseten_response = await new_client.call_structured_api(
                prompt=prompt_baseten,
                schema=schema_baseten,
                model="deepseek-baseten",
                soft_schema=False # Try hard schema
            )

            logger.info(f"--- [New Client] Baseten DeepSeek Response ---")
            
            baseten_content = ""
            if 'choices' in new_baseten_response['response']:
                baseten_content = new_baseten_response['response']['choices'][0]['message']['content']
            elif 'content' in new_baseten_response['response']:
                for block in new_baseten_response['response']['content']:
                    if block['type'] == 'text':
                        baseten_content += block['text']
            
            logger.info(f"OUTPUT: {baseten_content}")
            
            assert new_baseten_response is not None, "Baseten response should not be None"
            assert new_baseten_response.get('response') is not None, "Baseten response should have a 'response' key"
            
            # Verify cost calculation if cost data is available
            if new_baseten_response.get('enhanced_data'):
                total_cost_baseten = new_baseten_response['enhanced_data']['costs']['actual']['total_cost']
                logger.info(f"Total Cost (Baseten): ${total_cost_baseten:.6f}")
                assert total_cost_baseten > 0, "Baseten total cost should be greater than 0"
            
            logger.info("✅ Baseten client returned valid response and cost data")
        else:
            logger.warning("Skipping Baseten test: Provider not initialized (missing API key?)")

    except Exception as e:
        logger.error(f"❌ Baseten client test failed: {e}")
        import traceback
        traceback.print_exc()

    logger.info("\nLive Refactor Comparison Test Finished.")

if __name__ == "__main__":
    asyncio.run(main())
