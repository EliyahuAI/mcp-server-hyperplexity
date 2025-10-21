#!/usr/bin/env python3
"""
View prompts from latest test run.
"""
import json
import sys
from pathlib import Path
from glob import glob

def view_prompts():
    """Display prompts from the most recent test."""

    # Find latest test file
    test_files = glob('table_maker/output/local_tests/*.json')
    if not test_files:
        print("[ERROR] No test files found")
        return

    latest = max(test_files, key=lambda x: Path(x).stat().st_mtime)
    print(f"Loading: {latest}\n")

    with open(latest, 'r') as f:
        data = json.load(f)

    api_calls = data.get('api_calls', [])

    if not api_calls:
        print("[ERROR] No API calls found in test results")
        return

    print(f"Found {len(api_calls)} API call(s)\n")
    print("="*80)

    for idx, call in enumerate(api_calls, 1):
        desc = call.get('call_description', 'Unknown')
        model = call.get('model', 'unknown')
        prompt = call.get('prompt_used', '')

        print(f"\n{idx}. {desc}")
        print(f"   Model: {model}")
        print("-"*80)

        if prompt:
            print(prompt)
        else:
            print("[No prompt saved for this call]")

        print("="*80)

if __name__ == '__main__':
    view_prompts()
