#!/usr/bin/env python3
"""
Purge SQS Queues Script

This script purges all SQS queues related to the perplexity validator project.
Use this to clear stuck messages or reset the queue state during development.
"""

import boto3
import sys
import argparse
from botocore.exceptions import ClientError

def list_project_queues():
    """List all SQS queues related to the project"""
    sqs = boto3.client('sqs', region_name='us-east-1')
    
    try:
        response = sqs.list_queues()
        queue_urls = response.get('QueueUrls', [])
        
        # Filter for project-related queues
        project_queues = []
        keywords = ['perplexity', 'hyperplexity', 'config', 'validator']
        
        for queue_url in queue_urls:
            queue_name = queue_url.split('/')[-1].lower()
            if any(keyword in queue_name for keyword in keywords):
                project_queues.append(queue_url)
        
        return project_queues
    
    except ClientError as e:
        print(f"[ERROR] Failed to list queues: {e}")
        return []

def get_queue_attributes(queue_url):
    """Get queue attributes including message count"""
    sqs = boto3.client('sqs', region_name='us-east-1')
    
    try:
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        )
        
        attributes = response.get('Attributes', {})
        visible_messages = int(attributes.get('ApproximateNumberOfMessages', 0))
        invisible_messages = int(attributes.get('ApproximateNumberOfMessagesNotVisible', 0))
        
        return visible_messages, invisible_messages
    
    except ClientError as e:
        print(f"[ERROR] Failed to get queue attributes for {queue_url}: {e}")
        return 0, 0

def purge_queue(queue_url, dry_run=False):
    """Purge a single SQS queue"""
    sqs = boto3.client('sqs', region_name='us-east-1')
    queue_name = queue_url.split('/')[-1]
    
    # Get message count before purging
    visible, invisible = get_queue_attributes(queue_url)
    total_messages = visible + invisible
    
    print(f"Queue: {queue_name}")
    print(f"  Messages: {visible} visible, {invisible} in-flight, {total_messages} total")
    
    if total_messages == 0:
        print(f"  [SKIP] Queue is already empty")
        return True
    
    if dry_run:
        print(f"  [DRY-RUN] Would purge {total_messages} messages")
        return True
    
    try:
        sqs.purge_queue(QueueUrl=queue_url)
        print(f"  [SUCCESS] Queue purged")
        return True
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'PurgeQueueInProgress':
            print(f"  [WARNING] Purge already in progress for this queue")
            return True
        else:
            print(f"  [ERROR] Failed to purge: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Purge SQS queues for perplexity validator')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be purged without actually purging')
    parser.add_argument('--queue', type=str,
                       help='Purge specific queue by name (partial match)')
    parser.add_argument('--all', action='store_true',
                       help='Purge all project queues without confirmation')
    
    args = parser.parse_args()
    
    print("Perplexity Validator SQS Queue Purge Tool")
    print("=" * 50)
    
    # List all project queues
    project_queues = list_project_queues()
    
    if not project_queues:
        print("[INFO] No project-related queues found")
        return
    
    # Filter queues if specific queue requested
    if args.queue:
        filtered_queues = [q for q in project_queues if args.queue.lower() in q.lower()]
        if not filtered_queues:
            print(f"[ERROR] No queues found matching '{args.queue}'")
            print(f"Available queues:")
            for queue in project_queues:
                print(f"  - {queue.split('/')[-1]}")
            return
        project_queues = filtered_queues
    
    print(f"Found {len(project_queues)} queue(s):")
    for queue in project_queues:
        print(f"  - {queue.split('/')[-1]}")
    print()
    
    # Confirmation unless --all flag is used
    if not args.all and not args.dry_run:
        response = input("Are you sure you want to purge these queues? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return
    
    # Purge queues
    success_count = 0
    for queue_url in project_queues:
        if purge_queue(queue_url, dry_run=args.dry_run):
            success_count += 1
        print()
    
    # Summary
    if args.dry_run:
        print(f"[DRY-RUN] Would have processed {len(project_queues)} queue(s)")
    else:
        print(f"[SUMMARY] Successfully purged {success_count}/{len(project_queues)} queue(s)")
        
        if success_count < len(project_queues):
            print("[WARNING] Some queues failed to purge. Check the error messages above.")
            sys.exit(1)

if __name__ == "__main__":
    main()