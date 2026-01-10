#!/usr/bin/env python3
"""
Fetch CloudWatch logs for debugging.
Usage: python fetch_cloudwatch_logs.py [log_stream_name]
"""

import boto3
import sys
import json
from datetime import datetime

LOG_GROUP = "/aws/lambda/perplexity-validator-background-dev"

def list_recent_streams(limit=10):
    """List recent log streams."""
    client = boto3.client('logs', region_name='us-east-1')

    response = client.describe_log_streams(
        logGroupName=LOG_GROUP,
        orderBy='LastEventTime',
        descending=True,
        limit=limit
    )

    print(f"\n=== Recent Log Streams in {LOG_GROUP} ===\n")
    for i, stream in enumerate(response.get('logStreams', [])):
        name = stream['logStreamName']
        last_event = stream.get('lastEventTimestamp', 0)
        if last_event:
            last_event_time = datetime.fromtimestamp(last_event / 1000).strftime('%Y-%m-%d %H:%M:%S')
        else:
            last_event_time = 'N/A'
        print(f"{i+1}. {name}")
        print(f"   Last event: {last_event_time}\n")

    return response.get('logStreams', [])

def fetch_logs(stream_name, limit=200, from_head=True):
    """Fetch logs from a specific stream."""
    client = boto3.client('logs', region_name='us-east-1')

    print(f"\n=== Fetching logs from: {stream_name} (from_head={from_head}) ===\n")

    response = client.get_log_events(
        logGroupName=LOG_GROUP,
        logStreamName=stream_name,
        limit=limit,
        startFromHead=from_head  # True = from beginning
    )

    events = response.get('events', [])

    for event in events:
        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000).strftime('%H:%M:%S.%f')[:-3]
        message = event['message'].strip()
        print(f"[{timestamp}] {message}")

    print(f"\n=== Total: {len(events)} log entries ===")
    return events

def main():
    if len(sys.argv) > 1:
        stream_name = sys.argv[1]
        # Handle the CloudWatch console format
        if '[$LATEST]' in stream_name:
            # Already in correct format
            pass
        fetch_logs(stream_name)
    else:
        # List recent streams and let user choose
        streams = list_recent_streams()

        if streams:
            print("\nEnter stream number to fetch (or 0 to exit): ", end='')
            try:
                choice = int(input())
                if 1 <= choice <= len(streams):
                    fetch_logs(streams[choice-1]['logStreamName'])
            except (ValueError, EOFError):
                print("Listing only. Run with stream name to fetch logs.")

if __name__ == '__main__':
    main()
