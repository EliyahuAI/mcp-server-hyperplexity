#!/usr/bin/env python3
"""
Example usage of the config_generation module
This replaces Lambda invokes with direct function calls
"""

import asyncio
from config_generation import generate_config

async def main():
    # Example payload - same structure as Lambda invoke
    payload = {
        'table_analysis': {
            'basic_info': {'column_names': ['Name', 'Email', 'Age']},
            'column_analysis': {},
            'domain_info': {},
            'metadata': {}
        },
        'existing_config': None,  # Optional
        'instructions': 'Generate an optimal configuration',
        'session_id': 'test-session-123',
        'conversation_history': [],
        'latest_validation_results': None
    }
    
    # Direct async function call (no Lambda invoke needed)
    result = await generate_config(payload)
    
    if result['success']:
        print("Config generated successfully!")
        print(f"Updated config has {len(result['updated_config']['validation_targets'])} targets")
        print(f"Clarifying questions: {result['clarifying_questions'][:100]}...")
    else:
        print(f"Error: {result['error']}")

if __name__ == '__main__':
    asyncio.run(main())
