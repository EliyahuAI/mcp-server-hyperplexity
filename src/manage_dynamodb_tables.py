#!/usr/bin/env python3
"""
DynamoDB Table Management Utility for Perplexity Validator
Provides functions to view, clear, and manage validation and tracking tables.
"""

import boto3
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from botocore.exceptions import ClientError

# Table names
USER_VALIDATION_TABLE = "perplexity-validator-user-validation"
USER_TRACKING_TABLE = "perplexity-validator-user-tracking"
CALL_TRACKING_TABLE = "perplexity-validator-call-tracking"

def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def get_dynamodb_client(region="us-east-1"):
    """Get DynamoDB client"""
    return boto3.client('dynamodb', region_name=region)

def get_dynamodb_resource(region="us-east-1"):
    """Get DynamoDB resource"""
    return boto3.resource('dynamodb', region_name=region)

def list_all_tables():
    """List all DynamoDB tables"""
    try:
        dynamodb = get_dynamodb_client()
        response = dynamodb.list_tables()
        
        print("=== All DynamoDB Tables ===")
        for table_name in response['TableNames']:
            if 'perplexity-validator' in table_name:
                print(f"✅ {table_name}")
            else:
                print(f"   {table_name}")
        print()
        
        return response['TableNames']
    except Exception as e:
        print(f"Error listing tables: {e}")
        return []

def describe_table(table_name):
    """Get detailed table information"""
    try:
        dynamodb = get_dynamodb_client()
        response = dynamodb.describe_table(TableName=table_name)
        
        table = response['Table']
        print(f"\n=== Table: {table_name} ===")
        print(f"Status: {table['TableStatus']}")
        print(f"Item Count: {table.get('ItemCount', 'Unknown')}")
        print(f"Size (bytes): {table.get('TableSizeBytes', 'Unknown')}")
        print(f"Created: {table.get('CreationDateTime', 'Unknown')}")
        
        # Key schema
        print("\nKey Schema:")
        for key in table['KeySchema']:
            print(f"  {key['AttributeName']} ({key['KeyType']})")
        
        # Global Secondary Indexes
        if 'GlobalSecondaryIndexes' in table:
            print("\nGlobal Secondary Indexes:")
            for gsi in table['GlobalSecondaryIndexes']:
                print(f"  {gsi['IndexName']}")
                for key in gsi['KeySchema']:
                    print(f"    {key['AttributeName']} ({key['KeyType']})")
        
        # TTL
        if 'TimeToLiveSpecification' in table:
            ttl = table['TimeToLiveSpecification']
            if ttl.get('Enabled'):
                print(f"\nTTL: Enabled on '{ttl['AttributeName']}'")
        
        print()
        return table
        
    except Exception as e:
        print(f"Error describing table {table_name}: {e}")
        return None

def scan_table(table_name, limit=None):
    """Scan and display table contents"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)
        
        scan_kwargs = {}
        if limit:
            scan_kwargs['Limit'] = limit
        
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        print(f"\n=== {table_name} Contents ===")
        print(f"Items found: {len(items)}")
        
        if items:
            print("\nItems:")
            for i, item in enumerate(items, 1):
                print(f"\n--- Item {i} ---")
                print(json.dumps(item, indent=2, default=decimal_default))
        else:
            print("No items found.")
        
        print()
        return items
        
    except Exception as e:
        print(f"Error scanning table {table_name}: {e}")
        return []

def get_user_validation_records(email=None):
    """Get validation records for a specific email or all records"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(USER_VALIDATION_TABLE)
        
        if email:
            # Get specific email
            try:
                response = table.get_item(Key={'email': email})
                if 'Item' in response:
                    print(f"\n=== Validation Record for {email} ===")
                    print(json.dumps(response['Item'], indent=2, default=decimal_default))
                    return [response['Item']]
                else:
                    print(f"\n❌ No validation record found for {email}")
                    return []
            except Exception as e:
                print(f"Error getting validation record for {email}: {e}")
                return []
        else:
            # Get all records
            return scan_table(USER_VALIDATION_TABLE)
            
    except Exception as e:
        print(f"Error accessing validation table: {e}")
        return []

def get_user_tracking_records(email=None):
    """Get tracking records for a specific email or all records"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(USER_TRACKING_TABLE)
        
        if email:
            # Get specific email
            try:
                response = table.get_item(Key={'email': email})
                if 'Item' in response:
                    print(f"\n=== Tracking Record for {email} ===")
                    print(json.dumps(response['Item'], indent=2, default=decimal_default))
                    return [response['Item']]
                else:
                    print(f"\n❌ No tracking record found for {email}")
                    return []
            except Exception as e:
                print(f"Error getting tracking record for {email}: {e}")
                return []
        else:
            # Get all records
            return scan_table(USER_TRACKING_TABLE)
            
    except Exception as e:
        print(f"Error accessing tracking table: {e}")
        return []

def delete_user_validation_record(email):
    """Delete validation record for a specific email"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(USER_VALIDATION_TABLE)
        
        # Check if record exists first
        response = table.get_item(Key={'email': email})
        if 'Item' not in response:
            print(f"❌ No validation record found for {email}")
            return False
        
        # Delete the record
        table.delete_item(Key={'email': email})
        print(f"✅ Deleted validation record for {email}")
        return True
        
    except Exception as e:
        print(f"Error deleting validation record for {email}: {e}")
        return False

def delete_user_tracking_record(email):
    """Delete tracking record for a specific email"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(USER_TRACKING_TABLE)
        
        # Check if record exists first
        response = table.get_item(Key={'email': email})
        if 'Item' not in response:
            print(f"❌ No tracking record found for {email}")
            return False
        
        # Delete the record
        table.delete_item(Key={'email': email})
        print(f"✅ Deleted tracking record for {email}")
        return True
        
    except Exception as e:
        print(f"Error deleting tracking record for {email}: {e}")
        return False

def clear_table(table_name):
    """Clear all items from a table"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)
        
        # Get table key schema
        key_schema = table.key_schema
        key_names = [key['AttributeName'] for key in key_schema]
        
        # Scan and delete all items
        response = table.scan()
        items = response.get('Items', [])
        
        if not items:
            print(f"Table {table_name} is already empty.")
            return True
        
        print(f"Deleting {len(items)} items from {table_name}...")
        
        with table.batch_writer() as batch:
            for item in items:
                # Extract key attributes for deletion
                key = {key_name: item[key_name] for key_name in key_names}
                batch.delete_item(Key=key)
        
        print(f"✅ Cleared all {len(items)} items from {table_name}")
        return True
        
    except Exception as e:
        print(f"Error clearing table {table_name}: {e}")
        return False

def get_call_tracking_records(limit=10):
    """Get recent call tracking records"""
    try:
        return scan_table(CALL_TRACKING_TABLE, limit=limit)
    except Exception as e:
        print(f"Error accessing call tracking table: {e}")
        return []

def main():
    """Main function with command line interface"""
    if len(sys.argv) < 2:
        print("""
DynamoDB Table Management Utility

Usage:
    python manage_dynamodb_tables.py list                    # List all tables
    python manage_dynamodb_tables.py describe <table_name>   # Describe specific table
    python manage_dynamodb_tables.py scan <table_name>       # Scan table contents
    python manage_dynamodb_tables.py validation [email]      # Show validation records
    python manage_dynamodb_tables.py tracking [email]        # Show tracking records
    python manage_dynamodb_tables.py delete-validation <email>  # Delete validation record
    python manage_dynamodb_tables.py delete-tracking <email>    # Delete tracking record
    python manage_dynamodb_tables.py clear <table_name>      # Clear all items from table
    python manage_dynamodb_tables.py calls                   # Show recent call tracking
    python manage_dynamodb_tables.py summary                 # Show summary of all tables

Examples:
    python manage_dynamodb_tables.py validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py delete-validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py clear perplexity-validator-user-validation
        """)
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_all_tables()
    
    elif command == "describe":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py describe <table_name>")
            return
        table_name = sys.argv[2]
        describe_table(table_name)
    
    elif command == "scan":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py scan <table_name>")
            return
        table_name = sys.argv[2]
        scan_table(table_name)
    
    elif command == "validation":
        email = sys.argv[2] if len(sys.argv) > 2 else None
        get_user_validation_records(email)
    
    elif command == "tracking":
        email = sys.argv[2] if len(sys.argv) > 2 else None
        get_user_tracking_records(email)
    
    elif command == "delete-validation":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py delete-validation <email>")
            return
        email = sys.argv[2]
        delete_user_validation_record(email)
    
    elif command == "delete-tracking":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py delete-tracking <email>")
            return
        email = sys.argv[2]
        delete_user_tracking_record(email)
    
    elif command == "clear":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py clear <table_name>")
            return
        table_name = sys.argv[2]
        confirm = input(f"Are you sure you want to clear ALL items from {table_name}? (yes/no): ")
        if confirm.lower() == 'yes':
            clear_table(table_name)
        else:
            print("Operation cancelled.")
    
    elif command == "calls":
        get_call_tracking_records()
    
    elif command == "summary":
        print("=== DynamoDB Tables Summary ===\n")
        tables = list_all_tables()
        
        for table_name in [USER_VALIDATION_TABLE, USER_TRACKING_TABLE, CALL_TRACKING_TABLE]:
            if table_name in tables:
                describe_table(table_name)
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'python manage_dynamodb_tables.py' for help.")

if __name__ == "__main__":
    main() 