#!/usr/bin/env python3
"""
Check SQS queue status to see if config generation messages are being processed
"""

import boto3
import json
import time
from datetime import datetime

# SQS Queue URL
STANDARD_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/400232868802/perplexity-validator-standard-queue"

def check_sqs_status():
    """Check the status of SQS messages"""
    
    print("=" * 60)
    print("SQS Queue Status Check")
    print("=" * 60)
    print(f"Queue: {STANDARD_QUEUE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()
    
    try:
        sqs = boto3.client('sqs', region_name='us-east-1')
        
        # Get queue attributes
        response = sqs.get_queue_attributes(
            QueueUrl=STANDARD_QUEUE_URL,
            AttributeNames=[
                'ApproximateNumberOfMessages',
                'ApproximateNumberOfMessagesNotVisible',
                'ApproximateNumberOfMessagesDelayed'
            ]
        )
        
        attributes = response['Attributes']
        
        print("Queue Status:")
        print(f"  Messages available: {attributes.get('ApproximateNumberOfMessages', '0')}")
        print(f"  Messages in flight: {attributes.get('ApproximateNumberOfMessagesNotVisible', '0')}")
        print(f"  Messages delayed: {attributes.get('ApproximateNumberOfMessagesDelayed', '0')}")
        print()
        
        # Try to peek at a message without deleting it
        print("Checking for recent messages...")
        peek_response = sqs.receive_message(
            QueueUrl=STANDARD_QUEUE_URL,
            MaxNumberOfMessages=1,
            VisibilityTimeout=30,
            WaitTimeSeconds=1
        )
        
        if 'Messages' in peek_response:
            message = peek_response['Messages'][0]
            body = json.loads(message['Body'])
            
            print("Found a message:")
            print(f"  Request Type: {body.get('request_type', 'unknown')}")
            print(f"  Session ID: {body.get('session_id', 'unknown')}")
            print(f"  Created At: {body.get('created_at', 'unknown')}")
            print(f"  Generation Mode: {body.get('generation_mode', 'unknown')}")
            print()
            
            # Put the message back by not deleting it
            print("Message will be reprocessed by validation lambda")
            
            # Check how long this message has been in the queue
            if 'created_at' in body:
                try:
                    created_time = datetime.fromisoformat(body['created_at'].replace('Z', '+00:00'))
                    current_time = datetime.now()
                    # Simple comparison (ignoring timezone for rough estimate)
                    print(f"Message age: ~{(current_time - created_time.replace(tzinfo=None)).total_seconds():.0f} seconds")
                except:
                    print("Could not determine message age")
        else:
            print("No messages currently in queue")
            
    except Exception as e:
        print(f"Error checking SQS status: {e}")

if __name__ == "__main__":
    check_sqs_status()