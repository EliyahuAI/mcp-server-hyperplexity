#!/usr/bin/env python3
"""
Script to download CloudWatch logs for debugging Table Maker.
"""

import boto3
import json
from datetime import datetime

# Configure
LOG_GROUP = "/aws/lambda/perplexity-validator-background-dev"
LOG_STREAM = "2026/01/12/[$LATEST]44471ac693224a7f9ce56e963b492109"
OUTPUT_FILE = "cloudwatch_logs_debug.json"

def download_logs():
    """Download logs from CloudWatch."""
    client = boto3.client('logs', region_name='us-east-1')

    all_events = []
    next_token = None

    print(f"Downloading logs from: {LOG_GROUP}")
    print(f"Log stream: {LOG_STREAM}")

    while True:
        params = {
            'logGroupName': LOG_GROUP,
            'logStreamName': LOG_STREAM,
            'startFromHead': True
        }

        if next_token:
            params['nextToken'] = next_token

        response = client.get_log_events(**params)

        events = response.get('events', [])
        all_events.extend(events)

        # Check if we've reached the end
        new_token = response.get('nextForwardToken')
        if new_token == next_token or not events:
            break
        next_token = new_token

        print(f"  Downloaded {len(all_events)} events so far...")

    print(f"\nTotal events: {len(all_events)}")

    # Process events for readability
    processed_events = []
    for event in all_events:
        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000).isoformat()
        message = event['message']

        processed_events.append({
            'timestamp': timestamp,
            'message': message
        })

    # Save to file
    output = {
        'log_group': LOG_GROUP,
        'log_stream': LOG_STREAM,
        'event_count': len(processed_events),
        'events': processed_events
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {OUTPUT_FILE}")

    # Also print a summary
    print("\n" + "="*80)
    print("LOG SUMMARY")
    print("="*80 + "\n")

    for event in processed_events:
        msg = event['message'].strip()
        if msg:
            # Print just the message (skip timestamp prefix if Lambda adds one)
            if '\t' in msg:
                parts = msg.split('\t', 2)
                if len(parts) >= 3:
                    msg = parts[2]
            print(msg[:200])

    return output

if __name__ == "__main__":
    download_logs()
