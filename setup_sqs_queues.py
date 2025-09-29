#!/usr/bin/env python3
"""
Setup SQS Queues for Smart Delegation System

This script creates the necessary SQS queues for the smart delegation system:
1. Async Validator Queue - receives async validation requests and continuations
2. Interface Completion Queue - receives completion notifications for interface processing

Usage:
    python setup_sqs_queues.py [--region us-east-1] [--dry-run]
"""

import boto3
import json
import argparse
import sys
from botocore.exceptions import ClientError


def create_sqs_queue(sqs_client, queue_name, attributes=None, tags=None):
    """Create an SQS queue with specified attributes and tags."""
    try:
        print(f"Creating SQS queue: {queue_name}")

        # Default attributes
        default_attributes = {
            'MessageRetentionPeriod': '1209600',  # 14 days
            'VisibilityTimeout': '900',           # 15 minutes (match lambda timeout)
            'ReceiveMessageWaitTimeSeconds': '0'  # No long polling by default
        }

        # Merge with provided attributes
        if attributes:
            default_attributes.update(attributes)

        # Create queue
        response = sqs_client.create_queue(
            QueueName=queue_name,
            Attributes=default_attributes,
            tags=tags or {}
        )

        queue_url = response['QueueUrl']
        print(f"[SUCCESS] Created queue: {queue_url}")

        # Get queue attributes to display configuration
        attrs = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['All']
        )

        print(f"   Message Retention: {int(attrs['Attributes']['MessageRetentionPeriod']) / 86400:.0f} days")
        print(f"   Visibility Timeout: {attrs['Attributes']['VisibilityTimeout']} seconds")
        print(f"   Queue ARN: {attrs['Attributes']['QueueArn']}")

        return queue_url

    except ClientError as e:
        if e.response['Error']['Code'] == 'QueueAlreadyExists':
            print(f"[WARNING] Queue {queue_name} already exists")
            # Get existing queue URL
            try:
                response = sqs_client.get_queue_url(QueueName=queue_name)
                return response['QueueUrl']
            except ClientError:
                print(f"[ERROR] Failed to get existing queue URL for {queue_name}")
                return None
        else:
            print(f"[ERROR] Failed to create queue {queue_name}: {e}")
            return None
    except Exception as e:
        print(f"[ERROR] Unexpected error creating queue {queue_name}: {e}")
        return None


def setup_async_validator_queue(sqs_client, dry_run=False):
    """Setup the async validator queue."""
    queue_name = "perplexity-validator-async-queue"

    if dry_run:
        print(f"[DRY RUN] Would create async validator queue: {queue_name}")
        return f"https://sqs.us-east-1.amazonaws.com/123456789012/{queue_name}"

    # Configure for async validation processing
    attributes = {
        'MessageRetentionPeriod': '1209600',      # 14 days - keep messages for retry
        'VisibilityTimeout': '900',               # 15 minutes - match lambda timeout
        'ReceiveMessageWaitTimeSeconds': '20'     # Long polling to reduce API calls
    }

    tags = {
        'Project': 'PerplexityValidator',
        'Component': 'SmartDelegationSystem',
        'Purpose': 'AsyncValidationRequests'
    }

    print("\n[ASYNC QUEUE] Setting up Async Validator Queue")
    print("   Purpose: Receives async validation requests and continuations")
    print("   Triggered by: Background Handler (delegation), Validation Lambda (self-continuation)")
    print("   Processed by: Validation Lambda")

    return create_sqs_queue(sqs_client, queue_name, attributes, tags)


def setup_interface_completion_queue(sqs_client, dry_run=False):
    """Setup the interface completion queue."""
    queue_name = "perplexity-validator-completion-queue"

    if dry_run:
        print(f"[DRY RUN] Would create interface completion queue: {queue_name}")
        return f"https://sqs.us-east-1.amazonaws.com/123456789012/{queue_name}"

    # Configure for completion notifications
    attributes = {
        'MessageRetentionPeriod': '86400',        # 1 day - completion messages should be processed quickly
        'VisibilityTimeout': '300',               # 5 minutes - interface processing is faster
        'ReceiveMessageWaitTimeSeconds': '20'     # Long polling
    }

    tags = {
        'Project': 'PerplexityValidator',
        'Component': 'SmartDelegationSystem',
        'Purpose': 'CompletionNotifications'
    }

    print("\n[COMPLETION QUEUE] Setting up Interface Completion Queue")
    print("   Purpose: Receives completion notifications from async validation")
    print("   Triggered by: Validation Lambda (when processing complete)")
    print("   Processed by: Interface Lambda (async completion handler)")

    return create_sqs_queue(sqs_client, queue_name, attributes, tags)


def display_environment_variables(async_queue_url, completion_queue_url):
    """Display the environment variables needed for the lambdas."""
    print("\n" + "="*80)
    print("[CONFIG] ENVIRONMENT VARIABLES FOR LAMBDA FUNCTIONS")
    print("="*80)

    print("\n[VARIABLES] Add these to your Lambda environment variables:")
    print(f"ASYNC_VALIDATOR_QUEUE={async_queue_url}")
    print(f"INTERFACE_COMPLETION_QUEUE={completion_queue_url}")
    print("MAX_SYNC_INVOCATION_TIME=5.0")
    print("VALIDATOR_SAFETY_BUFFER=3.0")

    print("\n[FUNCTIONS] Lambda Functions that need these variables:")
    print("- perplexity-validator-interface (background_handler.py)")
    print("- perplexity-validator (validation lambda)")
    print("- perplexity-validator-async-completion (async_completion_handler.py)")

    print("\n[REMINDER] Remember to:")
    print("1. Update your deployment scripts with these environment variables")
    print("2. Ensure Lambda execution roles have SQS permissions")
    print("3. Configure SQS triggers for the validation lambda and completion handler")


def setup_iam_permissions_info():
    """Display information about required IAM permissions."""
    print("\n" + "="*80)
    print("[SECURITY] REQUIRED IAM PERMISSIONS")
    print("="*80)

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "sqs:SendMessage",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes"
                ],
                "Resource": [
                    "arn:aws:sqs:*:*:perplexity-validator-async-queue",
                    "arn:aws:sqs:*:*:perplexity-validator-completion-queue"
                ]
            }
        ]
    }

    print("Add this policy to your Lambda execution roles:")
    print(json.dumps(policy, indent=2))


def main():
    """Main function to setup SQS queues for smart delegation system."""
    parser = argparse.ArgumentParser(description='Setup SQS queues for Smart Delegation System')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created without actually creating')
    parser.add_argument('--skip-permissions-info', action='store_true', help='Skip displaying IAM permissions info')

    args = parser.parse_args()

    print("[SETUP] Smart Delegation System - SQS Queue Setup")
    print("="*60)
    print(f"Region: {args.region}")
    print(f"Dry Run: {args.dry_run}")
    print("")

    if args.dry_run:
        print("[WARNING] DRY RUN MODE - No resources will be created")
        print("")

    try:
        # Initialize SQS client
        sqs_client = boto3.client('sqs', region_name=args.region)

        # Test connection
        if not args.dry_run:
            sqs_client.list_queues(MaxResults=1)
            print("[SUCCESS] Successfully connected to AWS SQS")

        # Setup queues
        async_queue_url = setup_async_validator_queue(sqs_client, args.dry_run)
        completion_queue_url = setup_interface_completion_queue(sqs_client, args.dry_run)

        if async_queue_url and completion_queue_url:
            print("\n[SUCCESS] SQS Queue setup completed successfully!")
            display_environment_variables(async_queue_url, completion_queue_url)

            if not args.skip_permissions_info:
                setup_iam_permissions_info()

            print("\n[COMPLETE] Smart Delegation System SQS setup is complete!")
            print("   Next steps:")
            print("   1. Update Lambda environment variables")
            print("   2. Configure SQS triggers on Lambda functions")
            print("   3. Test the system with a large dataset")

        else:
            print("[ERROR] Failed to setup one or more queues")
            sys.exit(1)

    except ClientError as e:
        print(f"[ERROR] AWS Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()