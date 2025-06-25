#!/usr/bin/env python3
"""
Clean up duplicate Lambda permissions to fix policy size issue.
"""

import boto3
import json

def clean_lambda_permissions(function_name):
    """Remove all existing Lambda permissions to start fresh."""
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    try:
        # Get current policy
        response = lambda_client.get_policy(FunctionName=function_name)
        policy = json.loads(response['Policy'])
        
        print(f"Current policy has {len(policy['Statement'])} statements")
        print(f"Policy size: {len(response['Policy'])} bytes")
        
        # Remove each permission statement
        for statement in policy['Statement']:
            sid = statement['Sid']
            print(f"Removing permission: {sid}")
            try:
                lambda_client.remove_permission(
                    FunctionName=function_name,
                    StatementId=sid
                )
                print(f"  ✓ Removed {sid}")
            except Exception as e:
                print(f"  ✗ Failed to remove {sid}: {e}")
        
        print("\nAll permissions removed successfully!")
        
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"No policy found for function {function_name}")
    except Exception as e:
        print(f"Error cleaning permissions: {e}")

if __name__ == "__main__":
    # Clean up the interface Lambda
    clean_lambda_permissions('perplexity-validator-interface') 