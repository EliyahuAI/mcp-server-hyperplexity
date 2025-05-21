"""
Script to test Perplexity API response and examine the raw structure.
"""
import os
import json
import asyncio
import aiohttp
import logging
from pprint import pprint

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

async def validate_with_perplexity(prompt: str, api_key: str, model: str = "sonar-pro"):
    """Make a call to Perplexity API and return the full response."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Use the default schema but without response_format restriction 
    # to see what naturally comes back
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a data validation expert. Return your answer with sources."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    
    logger.info(f"Sending request to Perplexity API with model: {model}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        ) as response:
            response_text = await response.text()
            logger.info(f"API Response status: {response.status}")
            
            # Save the raw response to a file
            with open('perplexity_response_raw.json', 'w') as f:
                f.write(response_text)
                
            return json.loads(response_text)

async def test_multiplex_format():
    """Test with a simple multiplex format."""
    # Get API key from environment
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.error("No API key found in environment variables")
        return
    
    # Simple multiplex prompt
    prompt = """Please validate these two pieces of information:

1. Current CEO of Microsoft: Satya Nadella
2. Launch date of ChatGPT: November 30, 2022

For each, give me the correct answer, your confidence, and sources. Be sure to include citation numbers in your text and provide a references section at the end."""
    
    # Make the API call
    response = await validate_with_perplexity(prompt, api_key)
    
    # Save the full response to a file
    with open('perplexity_response_full.json', 'w') as f:
        json.dump(response, f, indent=2)
    
    print(f"Saved raw response to perplexity_response_raw.json")
    print(f"Saved parsed response to perplexity_response_full.json")
    
    # Check message structure
    if 'choices' in response and len(response['choices']) > 0:
        message = response['choices'][0]['message']
        
        # Save content to a text file
        with open('perplexity_response_content.txt', 'w') as f:
            f.write(message.get('content', ''))
            
        print(f"Saved response content to perplexity_response_content.txt")
        
        # Check for specific fields
        print("\n--- MESSAGE FIELDS ---")
        for key in message:
            print(f"Field: {key}")
            if key == 'content':
                print("Content: (showing first 100 chars)")
                print(message[key][:100] + "...")
            else:
                print(f"Value: {message[key]}")
    
        # Check if there are any citation-related fields
        print("\n--- CHECKING FOR CITATION FIELDS ---")
        citation_keys = [k for k in message if 'citation' in k.lower() or 'source' in k.lower() or 'reference' in k.lower()]
        if citation_keys:
            for k in citation_keys:
                print(f"Found citation field: {k}")
                print(message[k])
        else:
            print("No explicit citation fields found in the message structure")
    
async def main():
    await test_multiplex_format()

if __name__ == "__main__":
    asyncio.run(main()) 