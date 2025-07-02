#!/usr/bin/env python3
"""
Script to create DynamoDB tables for user email validation and tracking.
"""

import boto3
import logging
from dynamodb_schemas import (
    create_user_validation_table,
    create_user_tracking_table,
    DynamoDBSchemas
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Create the user validation and tracking tables."""
    print("Creating DynamoDB tables for user validation and tracking...")
    
    # Create user validation table
    print("\n1. Creating user validation table...")
    if create_user_validation_table():
        print(f"✅ {DynamoDBSchemas.USER_VALIDATION_TABLE} table created/verified")
    else:
        print(f"❌ Failed to create {DynamoDBSchemas.USER_VALIDATION_TABLE} table")
        return False
    
    # Create user tracking table
    print("\n2. Creating user tracking table...")
    if create_user_tracking_table():
        print(f"✅ {DynamoDBSchemas.USER_TRACKING_TABLE} table created/verified")
    else:
        print(f"❌ Failed to create {DynamoDBSchemas.USER_TRACKING_TABLE} table")
        return False
    
    print("\n✅ All user tables created successfully!")
    print("\nTable summary:")
    print(f"- {DynamoDBSchemas.USER_VALIDATION_TABLE}: Email validation with 6-digit codes (10 min TTL)")
    print(f"- {DynamoDBSchemas.USER_TRACKING_TABLE}: User usage statistics and access tracking")
    
    return True

if __name__ == "__main__":
    main() 