#!/usr/bin/env python3
"""
Debug Claude API response to see why web search isn't working
"""
import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / 'src'))
sys.path.append(str(Path(__file__).parent / 'src' / 'shared'))

from ai_api_client import AIAPIClient

async def debug_claude_response():
    """Debug the actual Claude API response structure"""
    print("=" * 60)
    print("DEBUGGING CLAUDE API RESPONSE STRUCTURE")
    print("=" * 60)
    
    client = AIAPIClient()
    
    # Very explicit web search prompt
    prompt = "Please use web search to find the latest news about ChatGPT from January 2025. I specifically need you to search the internet for current information."
    
    try:
        result = await client.call_text_api(
            prompt=prompt,
            model="claude-3-5-sonnet-20241022",
            use_cache=False
        )
        
        print("RESULT KEYS:", list(result.keys()))
        print()
        
        # Examine the raw API response structure
        raw_response = result.get('response', {})
        print("RAW RESPONSE TYPE:", type(raw_response))
        print("RAW RESPONSE KEYS:", list(raw_response.keys()) if isinstance(raw_response, dict) else "Not a dict")
        print()
        
        # Check content structure
        if 'content' in raw_response:
            content = raw_response['content']
            print("CONTENT TYPE:", type(content))
            print("CONTENT LENGTH:", len(content) if hasattr(content, '__len__') else "No length")
            
            if isinstance(content, list):
                print("CONTENT ITEMS:")
                for i, item in enumerate(content):
                    print(f"  [{i}] Type: {item.get('type', 'unknown')}")
                    if item.get('type') == 'tool_use':
                        print(f"      Tool Name: {item.get('name', 'unknown')}")
                        print(f"      Tool Input Keys: {list(item.get('input', {}).keys())}")
                    elif item.get('type') == 'tool_result':
                        print(f"      Tool Result Keys: {list(item.keys())}")
                    elif item.get('type') == 'text':
                        text_content = item.get('text', '')
                        print(f"      Text Length: {len(text_content)}")
                        print(f"      Text Preview: {text_content[:100]}...")
        
        # Check if there are any tool-related fields
        tool_fields = ['tools', 'tool_use', 'tool_result', 'tool_calls']
        for field in tool_fields:
            if field in raw_response:
                print(f"FOUND TOOL FIELD '{field}':", raw_response[field])
        
        # Check usage information
        if 'usage' in raw_response:
            usage = raw_response['usage']
            print("USAGE INFO:", usage)
        
        # Test citation extraction manually
        print("\n" + "=" * 40)
        print("MANUAL CITATION EXTRACTION TEST")
        print("=" * 40)
        
        citations = client.extract_citations_from_response(raw_response)
        print("EXTRACTED CITATIONS:", len(citations))
        
        if citations:
            for i, citation in enumerate(citations):
                print(f"  Citation {i+1}: {citation}")
        else:
            print("  No citations found")
        
        print("\nFULL RAW RESPONSE (first 1000 chars):")
        print(json.dumps(raw_response, indent=2)[:1000] + "...")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_claude_response())