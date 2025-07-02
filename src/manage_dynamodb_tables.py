#!/usr/bin/env python3
"""
DynamoDB Table Management Utility for Perplexity Validator
Provides functions to view, clear, and manage validation and tracking tables.
"""

import boto3
import json
import sys
import csv
import os
from datetime import datetime, timezone
from decimal import Decimal
from botocore.exceptions import ClientError

# Table names
USER_VALIDATION_TABLE = "perplexity-validator-user-validation"
USER_TRACKING_TABLE = "perplexity-validator-user-tracking"
CALL_TRACKING_TABLE = "perplexity-validator-call-tracking"

# Logical column ordering for CSV exports
USER_VALIDATION_COLUMNS = [
    # Identity
    'email',
    'validation_code',
    
    # Timestamps
    'created_at',
    'expires_at',
    'validated_at',
    'validation_requested_at',
    
    # Status
    'validated',
    'attempts',
    
    # System
    'ttl'
]

USER_TRACKING_COLUMNS = [
    # Identity
    'email',
    'email_domain',
    
    # Account Info
    'created_at',
    'last_access',
    
    # Email Validation History
    'first_email_validation_request',
    'most_recent_email_validation_request', 
    'first_email_validation',
    'most_recent_email_validation',
    
    # Usage Statistics
    'total_preview_requests',
    'total_full_requests',
    
    # Token Usage
    'total_tokens_used',
    'perplexity_tokens',
    'anthropic_tokens',
    
    # Cost Tracking
    'total_cost_usd',
    'perplexity_cost',
    'anthropic_cost'
]

CALL_TRACKING_COLUMNS = [
    # Session Identity
    'session_id',
    'reference_pin',
    'email',
    'email_domain',
    
    # Request Info
    'created_at',
    'request_type',
    'async_mode',
    'trigger_method',
    'trigger_source',
    
    # Processing Status & Timing
    'status',
    'started_processing_at',
    'processing_completed_at',
    'completed_processing_at',
    'response_sent_at',
    
    # File Information
    'original_excel_filename',
    'original_config_filename',
    'original_results_filename',
    'excel_file_size_bytes',
    'config_file_size_bytes',
    'results_file_size_bytes',
    
    # S3 Keys
    'excel_s3_key',
    'config_s3_key',
    'results_s3_key',
    
    # Processing Configuration
    'max_rows',
    'batch_size',
    'preview_max_rows',
    'validation_targets_count',
    
    # Processing Results
    'total_rows',
    'processed_rows',
    'new_rows_processed',
    'cached_rows',
    
    # Validation Results
    'high_confidence_count',
    'medium_confidence_count', 
    'low_confidence_count',
    'validation_accuracy_score',
    
    # Performance Metrics
    'processing_time_seconds',
    'validation_time_seconds',
    'file_upload_time_seconds',
    'result_creation_time_seconds',
    'queue_wait_time_seconds',
    'avg_time_per_row_seconds',
    
    # Cost & Token Summary
    'total_cost_usd',
    'total_tokens',
    'total_api_calls',
    'total_cached_calls',
    'avg_cost_per_row_usd',
    'avg_tokens_per_row',
    'cache_hit_rate',
    
    # Perplexity API Details
    'perplexity_cost_usd',
    'perplexity_total_tokens',
    'perplexity_prompt_tokens',
    'perplexity_completion_tokens',
    'perplexity_api_calls',
    'perplexity_cached_calls',
    'perplexity_models_used',
    
    # Anthropic API Details
    'anthropic_cost_usd',
    'anthropic_total_tokens',
    'anthropic_input_tokens',
    'anthropic_output_tokens',
    'anthropic_api_calls',
    'anthropic_cached_calls',
    'anthropic_cache_tokens',
    'anthropic_models_used',
    
    # Preview Estimates
    'preview_per_row_cost_usd',
    'preview_per_row_tokens',
    'preview_per_row_time_seconds',
    'preview_per_row_time_without_cache_seconds',
    'preview_estimated_total_cost_usd',
    'preview_estimated_total_tokens',
    'preview_estimated_total_time_hours',
    'preview_estimated_total_time_without_cache_hours',
    
    # Email Delivery
    'email_sent',
    'email_delivery_status',
    'email_message_id',
    'email_send_time_seconds',
    'email_bounce_reason',
    
    # System & Infrastructure
    'lambda_request_id',
    'lambda_duration',
    'lambda_billed_duration',
    'lambda_memory_used',
    'api_gateway_request_id',
    'sqs_message_id',
    'client_ip',
    'user_agent',
    
    # Error Tracking
    'error_count',
    'error_message',
    'error_messages',
    'retry_count',
    
    # Metadata
    'priority',
    'sequential_call',
    'search_context_usage',
    'search_group_counts',
    'version',
    'tags',
    'notes',
    'warnings',
    
    # Access Tracking
    'download_count',
    'last_downloaded_at',
    'expires_at',
    'updated_at',
    
    # Result Format
    'result_format'
]

def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def get_ordered_columns(table_name, items):
    """Get logically ordered columns for a specific table"""
    # Get all available columns from the data
    all_keys = set()
    for item in items:
        all_keys.update(item.keys())
    
    # Get the predefined order for this table
    if table_name == USER_VALIDATION_TABLE:
        column_order = USER_VALIDATION_COLUMNS
    elif table_name == USER_TRACKING_TABLE:
        column_order = USER_TRACKING_COLUMNS
    elif table_name == CALL_TRACKING_TABLE:
        column_order = CALL_TRACKING_COLUMNS
    else:
        # Fallback to alphabetical if table not recognized
        return sorted(list(all_keys))
    
    # Build ordered columns: predefined order first, then any extra columns alphabetically
    ordered_columns = []
    
    # Add columns in predefined order if they exist in the data
    for col in column_order:
        if col in all_keys:
            ordered_columns.append(col)
            all_keys.remove(col)
    
    # Add any remaining columns alphabetically at the end
    if all_keys:
        ordered_columns.extend(sorted(list(all_keys)))
    
    return ordered_columns

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

def export_table_to_csv(table_name, output_dir="exports", limit=None):
    """Export a DynamoDB table to CSV file"""
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_{timestamp}.csv"
        filepath = os.path.join(output_dir, filename)
        
        # Get table data
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)
        
        scan_kwargs = {}
        if limit:
            scan_kwargs['Limit'] = limit
        
        print(f"🔄 Scanning table {table_name}...")
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        if not items:
            print(f"❌ No items found in table {table_name}")
            return None
        
        print(f"📊 Found {len(items)} items to export")
        
        # Get logically ordered columns for this table
        fieldnames = get_ordered_columns(table_name, items)
        
        # Write to CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in items:
                # Convert Decimal objects to float for CSV compatibility
                csv_row = {}
                for key in fieldnames:
                    value = item.get(key, '')
                    if isinstance(value, Decimal):
                        csv_row[key] = float(value)
                    elif isinstance(value, dict) or isinstance(value, list):
                        # Convert complex objects to JSON strings
                        csv_row[key] = json.dumps(value, default=decimal_default)
                    else:
                        csv_row[key] = value
                writer.writerow(csv_row)
        
        print(f"✅ Successfully exported {len(items)} items to {filepath}")
        print(f"📁 Columns: {', '.join(fieldnames)}")
        return filepath
        
    except Exception as e:
        print(f"❌ Error exporting table {table_name} to CSV: {e}")
        return None

def export_all_tables_to_csv(output_dir="exports", limit=None):
    """Export all perplexity-validator tables to CSV files"""
    tables_to_export = [USER_VALIDATION_TABLE, USER_TRACKING_TABLE, CALL_TRACKING_TABLE]
    exported_files = []
    
    print(f"🚀 Starting export of all DynamoDB tables to {output_dir}/")
    print("=" * 60)
    
    for table_name in tables_to_export:
        print(f"\n📊 Exporting {table_name}...")
        filepath = export_table_to_csv(table_name, output_dir, limit)
        if filepath:
            exported_files.append(filepath)
    
    print("\n" + "=" * 60)
    print(f"🎉 Export complete! {len(exported_files)} files created:")
    for filepath in exported_files:
        file_size = os.path.getsize(filepath) / 1024  # KB
        print(f"   📄 {filepath} ({file_size:.1f} KB)")
    
    return exported_files

def export_user_data_to_csv(email, output_dir="exports"):
    """Export all data for a specific user email to CSV files"""
    print(f"🔍 Exporting all data for user: {email}")
    exported_files = []
    
    # Create user-specific directory
    user_dir = os.path.join(output_dir, f"user_{email.replace('@', '_at_').replace('.', '_')}")
    os.makedirs(user_dir, exist_ok=True)
    
    # Export user validation record
    validation_records = get_user_validation_records(email)
    if validation_records:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"validation_{email.replace('@', '_at_')}_{timestamp}.csv"
        filepath = os.path.join(user_dir, filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            if validation_records:
                fieldnames = list(validation_records[0].keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for record in validation_records:
                    csv_row = {}
                    for key, value in record.items():
                        if isinstance(value, Decimal):
                            csv_row[key] = float(value)
                        else:
                            csv_row[key] = value
                    writer.writerow(csv_row)
                
                exported_files.append(filepath)
                print(f"✅ Exported validation data to {filepath}")
    
    # Export user tracking record
    tracking_records = get_user_tracking_records(email)
    if tracking_records:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tracking_{email.replace('@', '_at_')}_{timestamp}.csv"
        filepath = os.path.join(user_dir, filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            if tracking_records:
                fieldnames = list(tracking_records[0].keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for record in tracking_records:
                    csv_row = {}
                    for key, value in record.items():
                        if isinstance(value, Decimal):
                            csv_row[key] = float(value)
                        else:
                            csv_row[key] = value
                    writer.writerow(csv_row)
                
                exported_files.append(filepath)
                print(f"✅ Exported tracking data to {filepath}")
    
    if exported_files:
        print(f"🎉 User data export complete! {len(exported_files)} files created in {user_dir}/")
    else:
        print(f"❌ No data found for user {email}")
    
    return exported_files

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
    
CSV Export Commands:
    python manage_dynamodb_tables.py export-csv <table_name> [limit]    # Export single table to CSV
    python manage_dynamodb_tables.py export-all-csv [limit]             # Export all tables to CSV
    python manage_dynamodb_tables.py export-user-csv <email>            # Export user data to CSV

Examples:
    python manage_dynamodb_tables.py validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py delete-validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py clear perplexity-validator-user-validation
    python manage_dynamodb_tables.py export-csv perplexity-validator-user-tracking
    python manage_dynamodb_tables.py export-all-csv 100
    python manage_dynamodb_tables.py export-user-csv eliyahu@eliyahu.ai
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
    
    elif command == "export-csv":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py export-csv <table_name> [limit]")
            return
        table_name = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
        export_table_to_csv(table_name, limit=limit)
    
    elif command == "export-all-csv":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        export_all_tables_to_csv(limit=limit)
    
    elif command == "export-user-csv":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py export-user-csv <email>")
            return
        email = sys.argv[2]
        export_user_data_to_csv(email)
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'python manage_dynamodb_tables.py' for help.")

if __name__ == "__main__":
    main() 