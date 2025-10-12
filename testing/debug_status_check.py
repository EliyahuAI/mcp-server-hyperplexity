#!/usr/bin/env python3
"""
Quick debug script to check status response format immediately after preview.
"""

import sys
import time
import json
sys.path.insert(0, '/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/testing')

from demo_api_client import DemoAPIClient

def main():
    client = DemoAPIClient(email="eliyahu@eliyahu.ai")

    print("=" * 70)
    print("DEBUG: Status Check Test")
    print("=" * 70)

    # Load demo
    print("\n[1] Loading demo...")
    session_id, demo_info = client.call_demo_api("01. Investment Research")

    # Trigger preview WITHOUT waiting
    print("\n[2] Triggering preview (no wait)...")

    # Create dummy file
    dummy_file = json.dumps({'use_stored_files': True}).encode('utf-8')
    files = {
        'dummy_file': ('stored_files_marker.json', dummy_file, 'application/json')
    }
    data = {
        'email': client.email,
        'session_id': session_id
    }
    params = {
        'async': 'true',
        'preview_first_row': 'true',
        'preview_max_rows': '3'
    }

    response = client._make_request(
        method='POST',
        endpoint='/validate',
        data=data,
        files=files,
        params=params,
        timeout=60
    )

    print(f"[PREVIEW TRIGGER RESPONSE]")
    print(json.dumps(response, indent=2))

    preview_session_id = response.get('session_id', session_id)

    # Check status immediately (0s), then at 1s, 2s, 3s, 5s, 10s
    for delay in [0, 1, 2, 3, 5, 10]:
        if delay > 0:
            print(f"\n[3] Waiting {delay}s before status check...")
            time.sleep(delay - (1 if delay > 1 else 0))  # Subtract previous wait
        else:
            print(f"\n[3] Checking status IMMEDIATELY (0s)...")

        try:
            status = client.check_status(preview_session_id, is_preview=True)
            print(f"\n[STATUS at {delay}s]")
            print(json.dumps(status, indent=2, default=str))

            # Check if completed
            status_str = status.get('status', '')
            has_preview = 'preview_data' in status
            has_download = 'download_url' in status

            print(f"\n[ANALYSIS]")
            print(f"  - Status field: {status_str}")
            print(f"  - Has preview_data: {has_preview}")
            print(f"  - Has download_url: {has_download}")
            print(f"  - Is completed: {status_str.upper() == 'COMPLETED' or has_preview or has_download}")

            if status_str.upper() == 'COMPLETED' or has_preview or has_download:
                print("\n[SUCCESS] Completion detected!")
                break

        except Exception as e:
            print(f"\n[ERROR at {delay}s] {e}")

    print("\n" + "=" * 70)

if __name__ == '__main__':
    main()
