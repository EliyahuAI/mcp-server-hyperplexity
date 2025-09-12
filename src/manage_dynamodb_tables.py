#!/usr/bin/env python3
"""
DynamoDB Table Management Utility for Perplexity Validator
Provides functions to view, clear, and manage validation and tracking tables.

For detailed table structure and schema documentation, see: docs/DYNAMODB_TABLES.md
"""

import boto3
import json
import sys
import csv
import os
from datetime import datetime, timezone
from decimal import Decimal
from botocore.exceptions import ClientError

# Import account management functions
try:
    from shared.dynamodb_schemas import (
        check_user_balance, add_to_balance, get_domain_multiplier, 
        set_domain_multiplier, DynamoDBSchemas,
        create_account_transactions_table, create_domain_multipliers_table
    )
    ACCOUNT_FUNCTIONS_AVAILABLE = True
except ImportError:
    ACCOUNT_FUNCTIONS_AVAILABLE = False

# Table names
USER_VALIDATION_TABLE = "perplexity-validator-user-validation"
USER_TRACKING_TABLE = "perplexity-validator-user-tracking"
CALL_TRACKING_TABLE = "perplexity-validator-call-tracking"
ACCOUNT_TRANSACTIONS_TABLE = "perplexity-validator-account-transactions"
DOMAIN_MULTIPLIERS_TABLE = "perplexity-validator-domain-multipliers"
RUNS_TABLE = "perplexity-validator-runs"
TOKEN_USAGE_TABLE = "perplexity-validator-token-usage"
WS_CONNECTIONS_TABLE = "perplexity-validator-ws-connections"
BATCH_AUDIT_TABLE = "perplexity-validator-batch-audit"
MODEL_CONFIG_TABLE = "perplexity-validator-model-config"

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
    
    # Request counts by type (using new field names)
    'total_previews',
    'total_validations',
    'total_configurations',
    
    # Enhanced validation metrics
    'total_rows_processed',
    'total_rows_analyzed',
    'total_columns_validated',
    'total_search_groups',
    'total_high_context_search_groups',
    'total_claude_calls',
    
    # Cost tracking with consolidated nomenclature
    'total_eliyahu_cost',
    'total_quoted_validation_cost',
    'total_validation_revenue',
    'total_config_eliyahu_cost',
    
    # Request-type specific metrics
    'preview_rows_processed',
    'preview_eliyahu_cost',
    'validation_rows_processed',
    'validation_revenue',
    'config_generation_eliyahu_cost',
    
    # API call tracking
    'total_api_calls_made',
    'total_cached_calls_made',
    
    # Account balance
    'account_balance',
    'balance_last_updated'
]

# Column order for runs table with consolidated schema
RUNS_TABLE_COLUMNS = [
    # Primary status info first
    'run_type',
    'run_time_s',
    'status',
    
    # Session Identity & Timing
    'session_id',
    'email',
    'start_time',
    'end_time',
    'last_update',
    
    # Progress tracking
    'verbose_status',
    'percent_complete',
    'processed_rows',
    'validated_columns_count',
    'total_rows',
    
    # API call counts
    'perplexity_calls',
    'anthropic_calls',
    'batch_size',
    
    # CONSOLIDATED: Cost and timing fields (ordered by importance)
    'eliyahu_cost',
    'estimated_validation_eliyahu_cost', 
    'quoted_validation_cost',
    'time_per_row_seconds',
    'estimated_validation_time_minutes',
    'run_time_s',
    
    # ENHANCED PROVIDER-SPECIFIC METRICS
    'total_provider_cost_actual',
    'total_provider_cost_estimated',
    'total_provider_calls',
    'total_provider_tokens',
    'overall_cache_efficiency_percent',
    
    # Provider-specific eliyahu costs (extracted from provider_metrics)
    'perplexity_eliyahu_cost',
    'anthropic_eliyahu_cost',
    
    # Account tracking
    'account_current_balance',
    'account_sufficient_balance',
    'account_credits_needed', 
    'account_domain_multiplier',
    
    # Model usage and input tracking
    'models',
    'input_table_name',
    'configuration_id',
    'results_s3_key',
    
    # Token usage details from flattened preview_data
    'perplexity_prompt_tokens',
    'perplexity_completion_tokens',
    'perplexity_per_row_estimated_cost',
    'anthropic_input_tokens',
    'anthropic_output_tokens',
    'anthropic_cache_creation_tokens',
    'anthropic_cache_read_tokens',
    'anthropic_per_row_estimated_cost',
    'search_groups_count',
    'enhanced_context_search_groups_count',
    'claude_search_groups_count',
    
    # Error handling
    'error_message'
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

def format_number_for_excel(value):
    """Format numbers to prevent Excel from using scientific notation"""
    if value is None or value == '':
        return ''
    
    try:
        # Convert to float if it's not already
        num_value = float(value)
        
        # For very small numbers close to zero, just return 0
        if abs(num_value) < 1e-10:
            return '0'
            
        # For integers or numbers that can be represented as integers
        if num_value == int(num_value):
            return str(int(num_value))
        
        # For numbers with decimals, use a reasonable precision
        # Excel shows scientific notation for numbers > 1e11 or < 1e-4
        if abs(num_value) >= 1e11:
            # For very large numbers, format with no decimal places if it's effectively an integer
            if num_value == int(num_value):
                return f"{int(num_value)}"
            else:
                return f"{num_value:.0f}"
        elif abs(num_value) < 1e-4:
            # For very small numbers, use scientific notation string to prevent Excel auto-conversion
            return f"{num_value:.2e}"
        else:
            # For normal range numbers, use appropriate decimal places
            if abs(num_value) >= 1000:
                return f"{num_value:.2f}"
            else:
                return f"{num_value:.6f}".rstrip('0').rstrip('.')
                
    except (ValueError, TypeError):
        return str(value)

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
    elif table_name == RUNS_TABLE:
        column_order = RUNS_TABLE_COLUMNS
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
                print(f"[SUCCESS] {table_name}")
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
                    print(f"\n[ERROR] No validation record found for {email}")
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
                    print(f"\n[ERROR] No tracking record found for {email}")
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
            print(f"[ERROR] No validation record found for {email}")
            return False
        
        # Delete the record
        table.delete_item(Key={'email': email})
        print(f"[SUCCESS] Deleted validation record for {email}")
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
            print(f"[ERROR] No tracking record found for {email}")
            return False
        
        # Delete the record
        table.delete_item(Key={'email': email})
        print(f"[SUCCESS] Deleted tracking record for {email}")
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
        
        print(f"[SUCCESS] Cleared all {len(items)} items from {table_name}")
        return True
        
    except Exception as e:
        print(f"Error clearing table {table_name}: {e}")

def delete_table(table_name):
    """Completely delete a DynamoDB table"""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        print(f"[INFO] Deleting table {table_name}...")
        table.delete()
        
        # Wait for table to be deleted
        print(f"[INFO] Waiting for table {table_name} to be completely deleted...")
        waiter = boto3.client('dynamodb').get_waiter('table_not_exists')
        waiter.wait(TableName=table_name)
        
        print(f"[SUCCESS] Table {table_name} has been completely deleted")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"[INFO] Table {table_name} does not exist")
            return True
        else:
            print(f"[ERROR] Failed to delete table {table_name}: {e}")
            return False
    except Exception as e:
        print(f"[ERROR] Error deleting table {table_name}: {e}")
        return False

def delete_runs_and_user_tables():
    """Delete both runs and user tracking tables"""
    tables_to_delete = [
        RUNS_TABLE,
        USER_TRACKING_TABLE
    ]
    
    print(f"[WARNING] This will COMPLETELY DELETE the following tables:")
    for table_name in tables_to_delete:
        print(f"  - {table_name}")
    print()
    
    confirm = input("Are you absolutely sure you want to DELETE these tables? Type 'DELETE TABLES' to confirm: ")
    if confirm != 'DELETE TABLES':
        print("[CANCELLED] Table deletion cancelled")
        return False
    
    success_count = 0
    for table_name in tables_to_delete:
        if delete_table(table_name):
            success_count += 1
    
    if success_count == len(tables_to_delete):
        print(f"\n[SUCCESS] All {len(tables_to_delete)} tables have been deleted")
        print("You can recreate them using the schema functions in dynamodb_schemas.py")
    else:
        print(f"\n[WARNING] Only {success_count}/{len(tables_to_delete)} tables were successfully deleted")
    
    return success_count == len(tables_to_delete)

def get_call_tracking_records(limit=10):
    """Get recent call tracking records"""
    try:
        return scan_table(CALL_TRACKING_TABLE, limit=limit)
    except Exception as e:
        print(f"Error accessing call tracking table: {e}")
        return []

def get_recent_runs_rich_table(limit=20):
    """Get recent validation runs with rich table display"""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(RUNS_TABLE)
        
        # Scan and get runs (get more than limit to ensure good sorting)
        scan_limit = max(limit * 3, 100) if limit else 100
        response = table.scan(Limit=scan_limit)
        items = response.get('Items', [])
        
        # Continue scanning if we need more items
        while 'LastEvaluatedKey' in response and len(items) < scan_limit:
            response = table.scan(
                Limit=scan_limit - len(items),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        if not items:
            print(f"[ERROR] No runs found in {RUNS_TABLE}")
            return []
        
        # Sort by start_time (most recent first) with better parsing
        def parse_timestamp(item):
            start_time_str = item.get('start_time', '')
            if not start_time_str:
                return '1970-01-01T00:00:00+00:00'  # Very old date for sorting
            # Handle various timestamp formats
            try:
                # Clean up the timestamp format
                if start_time_str.endswith('Z'):
                    start_time_str = start_time_str[:-1] + '+00:00'
                elif '+' not in start_time_str and 'T' in start_time_str:
                    start_time_str += '+00:00'
                return start_time_str
            except:
                return '1970-01-01T00:00:00+00:00'
        
        items.sort(key=parse_timestamp, reverse=True)
        
        # Take only the requested limit after sorting
        if limit:
            items = items[:limit]
        
        print(f"\n=== Recent Validation Runs ({len(items)} sessions, sorted by time) ===")
        print("=" * 140)
        
        # Better organized header with meaningful column order
        header = f"{'Date/Time':<17} {'Email':<22} {'Type':<8} {'Status':<11} {'Cost':<8} {'Tokens':<7} {'Cols':<5} {'Groups':<6} {'Duration':<8} {'Session ID':<25}"
        print(header)
        print("-" * 140)
        
        for i, item in enumerate(items, 1):
            # Parse and format timestamp
            start_time_str = item.get('start_time', '')
            date_time_display = "N/A"
            if start_time_str:
                try:
                    from datetime import datetime as dt
                    start_time = dt.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    date_time_display = start_time.strftime('%m/%d %H:%M:%S')
                except:
                    date_time_display = start_time_str[:16]
            
            # Email (truncated)
            email = item.get('email', 'N/A')
            email_display = email.split('@')[0][:15] + '@' + email.split('@')[1][:6] if '@' in email else email[:21]
            
            # Session type
            session_id = item.get('session_id', 'N/A')
            session_type = "Preview" if "preview" in session_id.lower() or item.get('total_rows', 0) == -1 else "Full"
            
            # Status
            status = item.get('status', 'N/A')[:10]
            
            # Extract metrics from preview_data
            preview_data = item.get('preview_data', {})
            cost_estimates = preview_data.get('cost_estimates', {})
            token_usage = preview_data.get('token_usage', {})
            validation_metrics = preview_data.get('validation_metrics', {})
            
            # Cost and tokens
            cost = 0.0  # Legacy preview_cost removed, use eliyahu_cost instead
            tokens = token_usage.get('total_tokens', 0)
            
            # Validation metrics
            cols = int(validation_metrics.get('validated_columns_count', 0))
            groups = int(validation_metrics.get('search_groups_count', 0))
            
            # Processing duration
            end_time_str = item.get('end_time', '')
            duration = "N/A"
            
            if start_time_str and end_time_str:
                try:
                    start_time = dt.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    end_time = dt.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    time_diff = (end_time - start_time).total_seconds()
                    if time_diff < 60:
                        duration = f"{time_diff:.1f}s"
                    elif time_diff < 3600:
                        duration = f"{time_diff/60:.1f}m"
                    else:
                        duration = f"{time_diff/3600:.1f}h"
                except:
                    duration = "N/A"
            
            # Format values for display
            cost_str = f"${cost:.3f}" if cost > 0 else "$0.000"
            tokens_str = f"{int(tokens/1000)}k" if tokens > 0 else "0"
            cols_str = str(cols) if cols > 0 else "-"
            groups_str = str(groups) if groups > 0 else "-"
            session_display = session_id[:24]
            
            # Print row with organized columns
            row = f"{date_time_display:<17} {email_display:<22} {session_type:<8} {status:<11} {cost_str:<8} {tokens_str:<7} {cols_str:<5} {groups_str:<6} {duration:<8} {session_display:<25}"
            print(row)
            
            # Add error details for failed sessions
            if status == "FAILED":
                error_msg = item.get('error_message', 'No error details')
                if error_msg and error_msg != 'No error details':
                    print(f"    [ERROR] {error_msg[:100]}")
        
        print("-" * 140)
        print(f"[SUCCESS] Showing {len(items)} most recent validation sessions (sorted by timestamp)")
        
        # Summary stats
        completed_sessions = sum(1 for item in items if item.get('status') == 'COMPLETED')
        failed_sessions = sum(1 for item in items if item.get('status') == 'FAILED')
        total_cost = sum(float(item.get('eliyahu_cost', 0)) for item in items)
        
        print(f"[STATS] Completed: {completed_sessions}, Failed: {failed_sessions}, Total Cost: ${total_cost:.3f}")
        
        return items
        
    except Exception as e:
        print(f"Error getting recent runs: {e}")
        return []

def display_enhanced_run_info(run_item):
    """Display comprehensive run information including enhanced provider metrics."""
    try:
        print(f"\n[SUCCESS] === RUN DETAILS ===")
        print(f"Session: {run_item.get('session_id', 'N/A')}")
        print(f"Run Key: {run_item.get('run_key', 'N/A')}")
        print(f"Type: {run_item.get('run_type', 'N/A')} | Status: {run_item.get('status', 'N/A')}")
        
        # Row processing info
        processed_rows = int(run_item.get('processed_rows', 0))
        total_rows = int(run_item.get('total_rows', 0))
        print(f"Rows: {processed_rows:,} / {total_rows:,}")
        
        # Cost breakdown with enhanced three-tier display
        eliyahu_cost = float(run_item.get('eliyahu_cost', 0))
        quoted_cost = float(run_item.get('quoted_validation_cost', 0))
        estimated_cost = float(run_item.get('estimated_validation_eliyahu_cost', 0))
        
        print(f"\n[COST BREAKDOWN]")
        print(f"  Costs: ${eliyahu_cost:.6f} (actual) | ${estimated_cost:.6f} (estimated) | ${quoted_cost:.2f} (quoted)")
        
        # Enhanced Provider-specific breakdown
        provider_metrics = run_item.get('provider_metrics', {})
        if provider_metrics and isinstance(provider_metrics, dict):
            print(f"\n[PROVIDER BREAKDOWN]")
            for provider, metrics in provider_metrics.items():
                if isinstance(metrics, dict):
                    cost_actual = float(metrics.get('cost_actual', 0))
                    cost_no_cache = float(metrics.get('cost_estimated', 0))
                    calls = int(metrics.get('calls', 0))
                    tokens = int(metrics.get('tokens', 0))
                    cache_eff = float(metrics.get('cache_efficiency_percent', 0))
                    
                    print(f"  {provider.upper()}:")
                    print(f"    Cost: ${cost_actual:.6f} (actual) / ${cost_no_cache:.6f} (no cache)")
                    print(f"    Usage: {calls} calls | {tokens:,} tokens")
                    print(f"    Cache Efficiency: {cache_eff:.1f}%")
                    
                    # Per-row metrics if available
                    cost_per_row_actual = metrics.get('cost_per_row_actual', 0)
                    time_per_row = metrics.get('time_per_row_actual', 0)
                    if cost_per_row_actual > 0:
                        print(f"    Per Row: ${float(cost_per_row_actual):.6f}/row, {float(time_per_row):.3f}s/row")
        else:
            # Fallback to aggregate totals if provider_metrics not available
            total_cost_actual = run_item.get('total_provider_cost_actual')
            total_cost_estimated = run_item.get('total_provider_cost_estimated')
            total_calls = run_item.get('total_provider_calls')
            total_tokens = run_item.get('total_provider_tokens')
            overall_cache_eff = run_item.get('overall_cache_efficiency_percent')
            
            if total_cost_actual is not None:
                print(f"\n[PROVIDER TOTALS]")
                print(f"  Total Cost: ${float(total_cost_actual):.6f} (actual) / ${float(total_cost_estimated or 0):.6f} (estimated)")
                print(f"  Total Usage: {int(total_calls or 0)} calls | {int(total_tokens or 0):,} tokens")
                print(f"  Overall Cache Efficiency: {float(overall_cache_eff or 0):.1f}%")
        
        # Timing information
        time_per_row = float(run_item.get('time_per_row_seconds', 0))
        estimated_time = float(run_item.get('estimated_validation_time_minutes', 0))
        run_time = float(run_item.get('run_time_s', 0))
        
        if time_per_row > 0 or estimated_time > 0 or run_time > 0:
            print(f"\n[TIMING]")
            if time_per_row > 0:
                print(f"  Time per Row: {time_per_row:.3f} seconds")
            if estimated_time > 0:
                print(f"  Estimated Time: {estimated_time:.1f} minutes")
            if run_time > 0:
                print(f"  Actual Runtime: {run_time:.1f} seconds")
        
        # Model usage
        models = run_item.get('models', '')
        if models:
            print(f"\n[MODELS USED]")
            print(f"  {models}")
        
        # Account information
        domain_multiplier = run_item.get('account_domain_multiplier')
        if domain_multiplier:
            print(f"\n[ACCOUNT INFO]")
            print(f"  Domain Multiplier: {float(domain_multiplier):.1f}x")
            
        # Configuration info
        config_id = run_item.get('configuration_id')
        table_name = run_item.get('input_table_name')
        if config_id or table_name:
            print(f"\n[CONFIGURATION]")
            if config_id:
                print(f"  Config ID: {config_id}")
            if table_name:
                print(f"  Table: {table_name}")
        
        print(f"" + "="*80)
        
    except Exception as e:
        print(f"[ERROR] Failed to display run info: {e}")

def list_runs_with_enhanced_sorting(limit=20, run_type_filter=None, status_filter=None):
    """List runs with intelligent sorting and filtering, showing enhanced provider metrics."""
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(RUNS_TABLE)
        
        # Get runs (scan more than needed for good sorting)
        scan_limit = max(limit * 3, 100) if limit else 100
        response = table.scan(Limit=scan_limit)
        runs = response.get('Items', [])
        
        # Continue scanning if there are more items
        while 'LastEvaluatedKey' in response and len(runs) < scan_limit:
            response = table.scan(
                Limit=scan_limit - len(runs),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            runs.extend(response.get('Items', []))
        
        if not runs:
            print(f"[ERROR] No runs found in {RUNS_TABLE}")
            return []
        
        # Apply filters
        if run_type_filter and run_type_filter.lower() not in ['all', '']:
            runs = [r for r in runs if run_type_filter.lower() in r.get('run_type', '').lower()]
            
        if status_filter and status_filter.upper() not in ['ALL', '']:
            runs = [r for r in runs if r.get('status', '').upper() == status_filter.upper()]
        
        # Sort runs: Most recent first, then by run type priority, then by cost
        def sort_key(run):
            # Primary: Most recent first (by last_update or start_time)
            last_update = run.get('last_update', run.get('start_time', '1970-01-01T00:00:00'))
            
            # Secondary: Run type priority (Validation=1, Preview=2, Config=3)
            run_type = run.get('run_type', 'Unknown')
            type_priority = {
                'Validation': 1, 
                'Preview': 2, 
                'Config Generation': 3, 
                'Config Refinement': 4
            }.get(run_type, 5)
            
            # Tertiary: Cost (highest first)
            cost = float(run.get('quoted_validation_cost', 0))
            
            return (last_update, type_priority, -cost)
        
        sorted_runs = sorted(runs, key=sort_key, reverse=True)
        
        # Limit results
        if limit:
            sorted_runs = sorted_runs[:limit]
        
        print(f"\n[SUCCESS] Found {len(sorted_runs)} runs matching criteria:")
        if run_type_filter:
            print(f"  Run Type Filter: {run_type_filter}")
        if status_filter:
            print(f"  Status Filter: {status_filter}")
        
        # Display each run with enhanced info
        for i, run in enumerate(sorted_runs, 1):
            print(f"\n[{i}/{len(sorted_runs)}]", end=" ")
            display_enhanced_run_info(run)
        
        return sorted_runs
        
    except Exception as e:
        print(f"[ERROR] Failed to list runs: {e}")
        return []

def show_dashboard():
    """Show comprehensive dashboard with user stats, recent runs, and system health"""
    try:
        print("\n" + "=" * 80)
        print("         PERPLEXITY VALIDATOR DASHBOARD")
        print("=" * 80)
        
        # 1. System Health Check
        print("\n[SYSTEM HEALTH]")
        tables_to_check = [
            (USER_TRACKING_TABLE, "User Tracking"),
            (RUNS_TABLE, "Validation Runs"),
            (ACCOUNT_TRANSACTIONS_TABLE, "Account Transactions"),
            (DOMAIN_MULTIPLIERS_TABLE, "Domain Multipliers"),
            (USER_VALIDATION_TABLE, "Email Validation"),
            (BATCH_AUDIT_TABLE, "Batch Size Audit"),
            (MODEL_CONFIG_TABLE, "Model Configuration"),
            (WS_CONNECTIONS_TABLE, "WebSocket Connections")
        ]
        
        for table_name, display_name in tables_to_check:
            try:
                dynamodb = get_dynamodb_client()
                response = dynamodb.describe_table(TableName=table_name)
                status = response['Table']['TableStatus']
                item_count = response['Table'].get('ItemCount', 0)
                size_bytes = response['Table'].get('TableSizeBytes', 0)
                size_kb = size_bytes / 1024 if size_bytes else 0
                
                status_icon = "[SUCCESS]" if status == "ACTIVE" else "[ERROR]"
                print(f"  {status_icon} {display_name:<25} | {item_count:>6} items | {size_kb:>8.1f} KB")
            except Exception as e:
                print(f"  [ERROR] {display_name:<25} | Failed to check: {str(e)[:40]}")
        
        # 2. User Activity Summary
        print("\n[USER ACTIVITY SUMMARY]")
        try:
            dynamodb = get_dynamodb_resource()
            user_table = dynamodb.Table(USER_TRACKING_TABLE)
            response = user_table.scan()
            users = response.get('Items', [])
            
            if users:
                total_users = len(users)
                total_preview_requests = sum(float(user.get('total_preview_requests', 0)) for user in users)
                total_full_requests = sum(float(user.get('total_full_requests', 0)) for user in users)
                total_cost = sum(float(user.get('total_cost_usd', 0)) for user in users)
                total_balance = sum(float(user.get('account_balance', 0)) for user in users)
                
                print(f"  Total Users:           {total_users}")
                print(f"  Total Preview Requests: {int(total_preview_requests)}")
                print(f"  Total Full Requests:   {int(total_full_requests)}")
                print(f"  Total Costs:           ${total_cost:.2f}")
                print(f"  Total Account Balance: ${total_balance:.2f}")
                
                # Most active users (sorted by total activity)
                users.sort(key=lambda x: float(x.get('total_preview_requests', 0)) + float(x.get('total_full_requests', 0)), reverse=True)
                print(f"\n  Most Active Users (by total requests):")
                for i, user in enumerate(users[:5], 1):
                    email = user.get('email', 'N/A')[:35]
                    preview_reqs = int(float(user.get('total_preview_requests', 0)))
                    full_reqs = int(float(user.get('total_full_requests', 0)))
                    balance = float(user.get('account_balance', 0))
                    last_access = user.get('last_access', 'N/A')
                    if last_access != 'N/A' and len(last_access) > 10:
                        try:
                            from datetime import datetime as dt
                            last_dt = dt.fromisoformat(last_access.replace('Z', '+00:00'))
                            last_access = last_dt.strftime('%m/%d/%y')
                        except:
                            last_access = last_access[:8]
                    print(f"    {i}. {email:<35} | {preview_reqs:>3}p + {full_reqs:>2}f | ${balance:>6.2f} | {last_access}")
            else:
                print("  No user data found")
        except Exception as e:
            print(f"  [ERROR] Failed to load user data: {e}")
        
        # 3. Recent Activity (last 15 runs, sorted by time)
        print("\n[RECENT ACTIVITY]")
        get_recent_runs_rich_table(15)
        
        # 4. Cost Analysis
        print("\n[COST ANALYSIS - Last 15 Sessions]")
        try:
            runs_table = dynamodb.Table(RUNS_TABLE)
            response = runs_table.scan(Limit=50)  # Get more to analyze
            runs = response.get('Items', [])
            
            if runs:
                # Sort by start_time and take last 15
                def parse_ts(x):
                    ts = x.get('start_time', '')
                    if ts.endswith('Z'):
                        ts = ts[:-1] + '+00:00'
                    return ts
                runs.sort(key=parse_ts, reverse=True)
                recent_runs = runs[:15]
                
                total_cost = 0
                total_tokens = 0
                provider_costs = {'perplexity': 0, 'anthropic': 0}
                
                for run in recent_runs:
                    preview_data = run.get('preview_data', {})
                    token_usage = preview_data.get('token_usage', {})
                    
                    cost = token_usage.get('total_cost', 0)
                    tokens = token_usage.get('total_tokens', 0)
                    
                    total_cost += float(cost)
                    total_tokens += float(tokens)
                    
                    # Provider breakdown
                    by_provider = token_usage.get('by_provider', {})
                    for provider, data in by_provider.items():
                        if provider in provider_costs:
                            provider_costs[provider] += float(data.get('total_cost', 0))
                
                print(f"  Total Cost (last 15):    ${total_cost:.3f}")
                print(f"  Total Tokens (last 15):  {int(total_tokens/1000)}k")
                print(f"  Average per session:     ${total_cost/15:.3f}")
                print(f"  Provider breakdown:")
                for provider, cost in provider_costs.items():
                    if cost > 0:
                        print(f"    {provider.capitalize()}: ${cost:.3f} ({cost/total_cost*100:.1f}%)")
            else:
                print("  No cost data available")
                
        except Exception as e:
            print(f"  [ERROR] Failed to analyze costs: {e}")
        
        print(f"\n[QUICK COMMANDS]")
        print(f"  python.exe src/manage_dynamodb_tables.py recent 25")
        print(f"  python.exe src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai")
        print(f"  python.exe src/manage_dynamodb_tables.py list-transactions eliyahu@eliyahu.ai")
        print(f"  python.exe src/manage_dynamodb_tables.py export-all-csv")
        
        print("\n" + "=" * 80)
        print("[SUCCESS] Dashboard loaded successfully")
        print("=" * 80)
        
    except Exception as e:
        print(f"[ERROR] Dashboard failed to load: {e}")

def extract_provider_cost(item, provider_name):
    """Extract eliyahu_cost for a specific provider from provider_metrics."""
    provider_metrics = item.get('provider_metrics', {})
    if provider_metrics and isinstance(provider_metrics, dict):
        provider_data = provider_metrics.get(provider_name, {})
        if isinstance(provider_data, dict):
            return float(provider_data.get('cost_actual', 0.0))
    return 0.0

def flatten_preview_data(item):
    """Extract and flatten rich data from preview_data field"""
    flattened = {}
    preview_data = item.get('preview_data', {})
    
    if not preview_data:
        return flattened
    
    # Cost estimates (cleaned up - obsolete fields removed from backend)
    cost_estimates = preview_data.get('cost_estimates', {})
    flattened.update({
        # Legacy preview_cost removed - use eliyahu_cost from top level
        'perplexity_per_row_estimated_cost': cost_estimates.get('perplexity_per_row_estimated_cost', 0),
        'anthropic_per_row_estimated_cost': cost_estimates.get('anthropic_per_row_estimated_cost', 0)
    })
    
    # Token usage by provider
    token_usage = preview_data.get('token_usage', {})
    by_provider = token_usage.get('by_provider', {})
    
    # Perplexity metrics (renamed cost field, removed total_tokens)
    perplexity = by_provider.get('perplexity', {})
    flattened.update({
        'perplexity_prompt_tokens': perplexity.get('prompt_tokens', 0),
        'perplexity_completion_tokens': perplexity.get('completion_tokens', 0),
        'perplexity_eliyahu_cost': extract_provider_cost(item, 'perplexity'),
        'perplexity_calls': perplexity.get('calls', 0)
    })
    
    # Anthropic metrics (renamed cost field, removed total_tokens)
    anthropic = by_provider.get('anthropic', {})
    flattened.update({
        'anthropic_input_tokens': anthropic.get('input_tokens', 0),
        'anthropic_output_tokens': anthropic.get('output_tokens', 0),
        'anthropic_cache_creation_tokens': anthropic.get('cache_creation_tokens', 0),
        'anthropic_cache_read_tokens': anthropic.get('cache_read_tokens', 0),
        'anthropic_eliyahu_cost': extract_provider_cost(item, 'anthropic'),
        'anthropic_calls': anthropic.get('calls', 0)
    })
    
    # Validation metrics
    validation_metrics = preview_data.get('validation_metrics', {})
    flattened.update({
        'search_groups_count': validation_metrics.get('search_groups_count', 0),
        'validated_columns_count': validation_metrics.get('validated_columns_count', 0),
        'enhanced_context_search_groups_count': validation_metrics.get('enhanced_context_search_groups_count', 0),
        'claude_search_groups_count': validation_metrics.get('claude_search_groups_count', 0)
    })
    
    # Processing times
    flattened.update({
        # Legacy timing fields removed - use run_time_s and estimated_validation_time_minutes
        'estimated_validation_time_minutes': preview_data.get('estimated_validation_time_minutes', 0)
    })
    
    # Account info (if present)
    account_info = preview_data.get('account_info', {})
    if account_info:
        flattened.update({
            'account_current_balance': account_info.get('current_balance', 0),
            'account_sufficient_balance': account_info.get('sufficient_balance', False),
            'account_credits_needed': account_info.get('credits_needed', 0),
            'account_domain_multiplier': account_info.get('domain_multiplier', 1)
        })
    
    return flattened

def export_table_to_csv(table_name, output_dir="events", limit=None):
    """Export a DynamoDB table to CSV file with rich data extraction"""
    try:
        # Create output directory with timestamp subfolder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, timestamp)
        os.makedirs(output_path, exist_ok=True)
        
        # Generate filename
        filename = f"{table_name}.csv"
        filepath = os.path.join(output_path, filename)
        
        # Get table data
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)
        
        scan_kwargs = {}
        if limit:
            scan_kwargs['Limit'] = limit
        
        print(f"[SCANNING] Scanning table {table_name}...")
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        if not items:
            print(f"[ERROR] No items found in table {table_name}")
            return None
        
        print(f"[INFO] Found {len(items)} items to export")
        
        # Enhanced processing for runs table to extract rich data
        if table_name == RUNS_TABLE:
            enhanced_items = []
            for item in items:
                enhanced_item = dict(item)
                # Remove the original preview_data field to avoid duplication
                enhanced_item.pop('preview_data', None)
                # Add flattened preview data
                enhanced_item.update(flatten_preview_data(item))
                enhanced_items.append(enhanced_item)
            items = enhanced_items
        
        # Sort items by timestamp (earliest first) for proper chronological order
        if table_name == RUNS_TABLE:
            def get_sort_time(item):
                start_time = item.get('start_time', '')
                if not start_time:
                    return '1970-01-01T00:00:00+00:00'
                try:
                    if start_time.endswith('Z'):
                        start_time = start_time[:-1] + '+00:00'
                    elif '+' not in start_time and 'T' in start_time:
                        start_time += '+00:00'
                    return start_time
                except:
                    return '1970-01-01T00:00:00+00:00'
            items.sort(key=get_sort_time)
        elif table_name == USER_TRACKING_TABLE:
            items.sort(key=lambda x: x.get('created_at', ''))
        elif table_name == ACCOUNT_TRANSACTIONS_TABLE:
            items.sort(key=lambda x: x.get('timestamp', ''))
        
        # Get logically ordered columns for this table
        fieldnames = get_ordered_columns(table_name, items)
        
        # Write to CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in items:
                # Convert Decimal objects to float for CSV compatibility and prevent Excel scientific notation
                csv_row = {}
                for key in fieldnames:
                    value = item.get(key, '')
                    if isinstance(value, Decimal):
                        # Convert to float first
                        float_value = float(value)
                        # Format large numbers to prevent Excel scientific notation
                        csv_row[key] = format_number_for_excel(float_value)
                    elif isinstance(value, (int, float)) and key in ['anthropic_input_tokens', 'anthropic_output_tokens', 'anthropic_total_tokens', 
                                                                      'perplexity_prompt_tokens', 'perplexity_completion_tokens', 'perplexity_total_tokens',
                                                                      'estimated_total_tokens', 'preview_tokens']:
                        # Format token fields that are large numbers to prevent scientific notation
                        csv_row[key] = format_number_for_excel(value)
                    elif isinstance(value, dict) or isinstance(value, list):
                        # Convert complex objects to JSON strings
                        csv_row[key] = json.dumps(value, default=decimal_default)
                    else:
                        csv_row[key] = value
                writer.writerow(csv_row)
        
        print(f"[SUCCESS] Successfully exported {len(items)} items to {filepath}")
        print(f"[INFO] Columns: {', '.join(fieldnames[:10])}{' ...' if len(fieldnames) > 10 else ''}")
        return filepath
        
    except Exception as e:
        print(f"[ERROR] Error exporting table {table_name} to CSV: {e}")
        return None

def export_all_tables_to_csv(output_dir="events", limit=None):
    """Export all perplexity-validator tables to CSV files with rich data"""
    tables_to_export = [
        USER_VALIDATION_TABLE, USER_TRACKING_TABLE, RUNS_TABLE,
        ACCOUNT_TRANSACTIONS_TABLE, DOMAIN_MULTIPLIERS_TABLE,
        TOKEN_USAGE_TABLE, WS_CONNECTIONS_TABLE, BATCH_AUDIT_TABLE,
        MODEL_CONFIG_TABLE
    ]
    exported_files = []
    
    # Create timestamped directory - single timestamp for all exports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, timestamp)
    os.makedirs(output_path, exist_ok=True)
    
    print(f"[EXPORTING] Starting export of all DynamoDB tables to {output_path}/")
    print("=" * 80)
    
    for table_name in tables_to_export:
        print(f"\n[EXPORTING] Exporting {table_name}...")
        try:
            # Get table data
            dynamodb = get_dynamodb_resource()
            table = dynamodb.Table(table_name)
            
            scan_kwargs = {}
            if limit:
                scan_kwargs['Limit'] = limit
            
            print(f"[SCANNING] Scanning table {table_name}...")
            response = table.scan(**scan_kwargs)
            items = response.get('Items', [])
            
            if not items:
                print(f"[ERROR] No items found in table {table_name}")
                continue
            
            print(f"[INFO] Found {len(items)} items to export")
            
            # Enhanced processing for runs table to extract rich data
            if table_name == RUNS_TABLE:
                enhanced_items = []
                for item in items:
                    enhanced_item = dict(item)
                    # Remove the original preview_data field to avoid duplication
                    enhanced_item.pop('preview_data', None)
                    # Add flattened preview data
                    enhanced_item.update(flatten_preview_data(item))
                    enhanced_items.append(enhanced_item)
                items = enhanced_items
            
            # Sort items by timestamp (earliest first) for proper chronological order
            if table_name == RUNS_TABLE:
                def get_sort_time(item):
                    start_time = item.get('start_time', '')
                    if not start_time:
                        return '1970-01-01T00:00:00+00:00'
                    try:
                        if start_time.endswith('Z'):
                            start_time = start_time[:-1] + '+00:00'
                        elif '+' not in start_time and 'T' in start_time:
                            start_time += '+00:00'
                        return start_time
                    except:
                        return '1970-01-01T00:00:00+00:00'
                items.sort(key=get_sort_time)
            elif table_name == USER_TRACKING_TABLE:
                items.sort(key=lambda x: x.get('created_at', ''))
            elif table_name == ACCOUNT_TRANSACTIONS_TABLE:
                items.sort(key=lambda x: x.get('timestamp', ''))
            
            # Get logically ordered columns for this table
            fieldnames = get_ordered_columns(table_name, items)
            
            # Generate filename
            filename = f"{table_name}.csv"
            filepath = os.path.join(output_path, filename)
            
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
            
            print(f"[SUCCESS] Successfully exported {len(items)} items to {filepath}")
            print(f"[INFO] Columns: {', '.join(fieldnames[:10])}{' ...' if len(fieldnames) > 10 else ''}")
            exported_files.append(filepath)
            
        except Exception as e:
            print(f"[ERROR] Error exporting table {table_name} to CSV: {e}")
    
    # Create summary file
    summary_file = os.path.join(output_path, "export_summary.txt")
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(f"DynamoDB Export Summary\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Export Directory: {output_path}\n")
        f.write(f"Tables Exported: {len(exported_files)}\n\n")
        
        for filepath in exported_files:
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath) / 1024
                item_count = sum(1 for line in open(filepath, 'r', encoding='utf-8')) - 1  # Subtract header
                f.write(f"{os.path.basename(filepath)}: {item_count} items, {file_size:.1f} KB\n")
    
    print("\n" + "=" * 80)
    print(f"[SUCCESS] Export complete! {len(exported_files)} files created in {output_path}/")
    for filepath in exported_files:
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath) / 1024
            print(f"   [FILE] {os.path.basename(filepath)} ({file_size:.1f} KB)")
    
    print(f"[INFO] Summary written to: {summary_file}")
    return exported_files

def export_user_data_to_csv(email, output_dir="exports"):
    """Export all data for a specific user email to CSV files"""
    print(f"[EXPORTING] Exporting all data for user: {email}")
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
                print(f"[SUCCESS] Exported validation data to {filepath}")
    
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
                print(f"[SUCCESS] Exported tracking data to {filepath}")
    
    if exported_files:
        print(f"[SUCCESS] User data export complete! {len(exported_files)} files created in {user_dir}/")
    else:
        print(f"[ERROR] No data found for user {email}")
    
    return exported_files

def get_account_transactions(email, limit=50):
    """Get account transactions for a specific email"""
    try:
        if not ACCOUNT_FUNCTIONS_AVAILABLE:
            print("[ERROR] Account management functions not available")
            return []
        
        from shared.dynamodb_schemas import get_user_transactions
        items = get_user_transactions(email.lower(), limit)
        
        print(f"\n=== Account Transactions for {email} ===")
        if items:
            print(f"Found {len(items)} transactions:\n")
            for i, transaction in enumerate(items, 1):
                timestamp = transaction.get('timestamp', 'Unknown')
                amount = transaction.get('amount', 0)
                balance_after = transaction.get('balance_after', 0)
                description = transaction.get('description', 'No description')
                transaction_type = transaction.get('transaction_type', 'unknown')
                session_id = transaction.get('session_id', 'N/A')
                
                # Format amount with + or - prefix
                amount_str = f"+${float(amount):.4f}" if amount >= 0 else f"-${float(abs(amount)):.4f}"
                
                print(f"{i:3d}. {timestamp[:19]}  {amount_str:>12}  Balance: ${float(balance_after):.4f}")
                print(f"     Type: {transaction_type}, Session: {session_id}")
                print(f"     {description}")
                print()
        else:
            print("No transactions found.")
        
        return items
        
    except Exception as e:
        print(f"Error getting account transactions: {e}")
        return []

def check_balance_command(email):
    """Check account balance for a user"""
    if not ACCOUNT_FUNCTIONS_AVAILABLE:
        print("[ERROR] Account management functions not available")
        return
    
    try:
        balance = check_user_balance(email)
        if balance is not None:
            print(f"\n=== Account Balance for {email} ===")
            print(f"Current Balance: ${float(balance):.4f}")
        else:
            print(f"[ERROR] User {email} not found in tracking table")
    except Exception as e:
        print(f"Error checking balance: {e}")

def add_balance_command(email, amount):
    """Add balance to user account"""
    if not ACCOUNT_FUNCTIONS_AVAILABLE:
        print("[ERROR] Account management functions not available")
        return
    
    try:
        amount_decimal = Decimal(str(amount))
        if amount_decimal <= 0:
            print("[ERROR] Amount must be positive")
            return
        
        success = add_to_balance(
            email=email,
            amount=amount_decimal,
            transaction_type='admin_credit',
            description=f'Manual credit added by admin via CLI'
        )
        
        if success:
            # Show new balance
            new_balance = check_user_balance(email)
            print(f"[SUCCESS] Added ${float(amount_decimal):.4f} to {email}")
            print(f"New balance: ${float(new_balance):.4f}")
        else:
            print("[ERROR] Failed to add balance")
            
    except (ValueError, TypeError):
        print("[ERROR] Invalid amount format")
    except Exception as e:
        print(f"Error adding balance: {e}")

def set_multiplier_command(domain, multiplier):
    """Set domain-specific cost multiplier"""
    if not ACCOUNT_FUNCTIONS_AVAILABLE:
        print("[ERROR] Account management functions not available")
        return
    
    try:
        multiplier_decimal = Decimal(str(multiplier))
        if multiplier_decimal <= 0:
            print("[ERROR] Multiplier must be positive")
            return
        
        success = set_domain_multiplier(
            domain=domain,
            multiplier=multiplier_decimal,
            admin_email='admin@cli',
            notes=f'Set via CLI on {datetime.now().isoformat()}'
        )
        
        if success:
            print(f"[SUCCESS] Set cost multiplier for '{domain}' to {float(multiplier_decimal)}x")
        else:
            print("[ERROR] Failed to set multiplier")
            
    except (ValueError, TypeError):
        print("[ERROR] Invalid multiplier format")
    except Exception as e:
        print(f"Error setting multiplier: {e}")

def get_multiplier_command(domain):
    """Get cost multiplier for a domain"""
    if not ACCOUNT_FUNCTIONS_AVAILABLE:
        print("[ERROR] Account management functions not available")
        return
    
    try:
        multiplier = get_domain_multiplier(domain)
        print(f"\n=== Cost Multiplier for '{domain}' ===")
        print(f"Multiplier: {float(multiplier)}x")
    except Exception as e:
        print(f"Error getting multiplier: {e}")

def create_account_tables():
    """Create account management tables"""
    if not ACCOUNT_FUNCTIONS_AVAILABLE:
        print("[ERROR] Account management functions not available")
        return
    
    print("Creating account management tables...")
    
    # Create account transactions table
    try:
        result = create_account_transactions_table()
        if result:
            print("[SUCCESS] Account transactions table created/verified")
        else:
            print("[ERROR] Failed to create account transactions table")
    except Exception as e:
        print(f"Error creating account transactions table: {e}")
    
    # Create domain multipliers table  
    try:
        result = create_domain_multipliers_table()
        if result:
            print("[SUCCESS] Domain multipliers table created/verified")
        else:
            print("[ERROR] Failed to create domain multipliers table")
    except Exception as e:
        print(f"Error creating domain multipliers table: {e}")
    
    print("\nAccount tables setup complete!")

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
    python manage_dynamodb_tables.py delete-table <table_name>  # COMPLETELY DELETE a table
    python manage_dynamodb_tables.py delete-runs-and-user-tables  # DELETE runs and user tracking tables
    python manage_dynamodb_tables.py calls                   # Show recent call tracking (legacy)
    python manage_dynamodb_tables.py recent [limit]          # Show recent validation runs (rich format)
    python manage_dynamodb_tables.py recent-calls [limit]    # Same as recent
    python manage_dynamodb_tables.py enhanced-runs [limit] [run_type] [status]  # Show enhanced runs with provider metrics
    python manage_dynamodb_tables.py dashboard              # Show comprehensive dashboard
    python manage_dynamodb_tables.py summary                 # Show summary of all tables
    
CSV Export Commands:
    python manage_dynamodb_tables.py export-csv <table_name> [limit]    # Export single table to CSV
    python manage_dynamodb_tables.py export-all-csv [limit]             # Export all tables to CSV
    python manage_dynamodb_tables.py export-user-csv <email>            # Export user data to CSV
    
Account Management Commands:
    python manage_dynamodb_tables.py check-balance <email>              # Check user's current balance
    python manage_dynamodb_tables.py add-balance <email> <amount>       # Add credits to user account
    python manage_dynamodb_tables.py list-transactions <email> [limit]  # View transaction history
    python manage_dynamodb_tables.py set-multiplier <domain> <multiplier> # Set domain cost multiplier
    python manage_dynamodb_tables.py get-multiplier <domain>            # Get domain cost multiplier
    python manage_dynamodb_tables.py set-global-multiplier <multiplier> # Set global cost multiplier
    python manage_dynamodb_tables.py create-account-tables              # Create account management tables
    
Batch Size Audit Commands:
    python manage_dynamodb_tables.py batch-history <model> [limit]      # View batch size history for model
    python manage_dynamodb_tables.py recent-batch-changes [hours] [limit] # Recent batch changes across all models  
    python manage_dynamodb_tables.py create-batch-audit-table           # Create batch audit table

Model Configuration Management Commands:
    python manage_dynamodb_tables.py load-model-config <csv_file>       # Load model configurations from CSV
    python manage_dynamodb_tables.py list-model-configs                 # List all model configurations
    python manage_dynamodb_tables.py test-model-config <model_name>     # Test model pattern matching
    python manage_dynamodb_tables.py create-model-config-table          # Create model config table

Examples:
    python manage_dynamodb_tables.py validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py delete-validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py clear perplexity-validator-user-validation
    python manage_dynamodb_tables.py export-csv perplexity-validator-user-tracking
    python manage_dynamodb_tables.py export-all-csv 100
    python manage_dynamodb_tables.py export-user-csv eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py enhanced-runs 10 validation completed
    
    python manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py add-balance eliyahu@eliyahu.ai 25.50
    python manage_dynamodb_tables.py list-transactions eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py set-multiplier eliyahu.ai 3.0
    python manage_dynamodb_tables.py get-multiplier eliyahu.ai
    python manage_dynamodb_tables.py set-global-multiplier 5.0
    python manage_dynamodb_tables.py create-account-tables
    
    python manage_dynamodb_tables.py batch-history claude-4-opus 10
    python manage_dynamodb_tables.py recent-batch-changes 24 20
    python manage_dynamodb_tables.py load-model-config src/config/unified_model_config.csv
    python manage_dynamodb_tables.py list-model-configs
    python manage_dynamodb_tables.py test-model-config claude-4-sonnet
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
    
    elif command == "delete-table":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py delete-table <table_name>")
            return
        table_name = sys.argv[2]
        confirm = input(f"Are you sure you want to COMPLETELY DELETE table {table_name}? (yes/no): ")
        if confirm.lower() == 'yes':
            delete_table(table_name)
        else:
            print("Operation cancelled.")
    
    elif command == "delete-runs-and-user-tables":
        delete_runs_and_user_tables()
    
    elif command == "calls":
        get_call_tracking_records()
    
    elif command == "recent" or command == "recent-calls":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        get_recent_runs_rich_table(limit)
    
    elif command == "enhanced-runs":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        run_type_filter = sys.argv[3] if len(sys.argv) > 3 else None
        status_filter = sys.argv[4] if len(sys.argv) > 4 else None
        list_runs_with_enhanced_sorting(limit, run_type_filter, status_filter)
    
    elif command == "dashboard":
        show_dashboard()
    
    elif command == "summary":
        print("=== DynamoDB Tables Summary ===\n")
        tables = list_all_tables()
        
        for table_name in [USER_VALIDATION_TABLE, USER_TRACKING_TABLE, RUNS_TABLE]:
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
    
    # Account Management Commands
    elif command == "check-balance":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py check-balance <email>")
            return
        email = sys.argv[2]
        check_balance_command(email)
    
    elif command == "add-balance":
        if len(sys.argv) < 4:
            print("Usage: python manage_dynamodb_tables.py add-balance <email> <amount>")
            return
        email = sys.argv[2]
        try:
            amount = float(sys.argv[3])
            add_balance_command(email, amount)
        except ValueError:
            print("[ERROR] Amount must be a valid number")
    
    elif command == "list-transactions":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py list-transactions <email> [limit]")
            return
        email = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        get_account_transactions(email, limit)
    
    elif command == "set-multiplier":
        if len(sys.argv) < 4:
            print("Usage: python manage_dynamodb_tables.py set-multiplier <domain> <multiplier>")
            return
        domain = sys.argv[2]
        try:
            multiplier = float(sys.argv[3])
            set_multiplier_command(domain, multiplier)
        except ValueError:
            print("[ERROR] Multiplier must be a valid number")
    
    elif command == "get-multiplier":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py get-multiplier <domain>")
            return
        domain = sys.argv[2]
        get_multiplier_command(domain)
    
    elif command == "set-global-multiplier":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py set-global-multiplier <multiplier>")
            return
        try:
            multiplier = float(sys.argv[2])
            set_multiplier_command('global', multiplier)
        except ValueError:
            print("[ERROR] Multiplier must be a valid number")
    
    elif command == "create-account-tables":
        create_account_tables()
    
    elif command == "batch-history":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py batch-history <model_name> [limit]")
            return
        model_name = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        get_batch_audit_history(model_name, limit)
    
    elif command == "recent-batch-changes":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        get_recent_batch_changes(hours, limit)
    
    elif command == "create-batch-audit-table":
        create_batch_audit_table_command()
    
    elif command == "load-model-config":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py load-model-config <csv_file_path>")
            return
        csv_file_path = sys.argv[2]
        load_model_config_command(csv_file_path)
    
    elif command == "list-model-configs":
        list_model_configs_command()
    
    elif command == "test-model-config":
        if len(sys.argv) < 3:
            print("Usage: python manage_dynamodb_tables.py test-model-config <model_name>")
            return
        model_name = sys.argv[2]
        test_model_config_command(model_name)
    
    elif command == "create-model-config-table":
        create_model_config_table_command()
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'python manage_dynamodb_tables.py' for help.")

def get_batch_audit_history(model_name, limit=50):
    """Get batch size change history for a specific model."""
    try:
        from shared.batch_audit_logger import BatchAuditLogger
        audit_logger = BatchAuditLogger()
        
        history = audit_logger.get_model_history(model_name, limit)
        
        print(f"\n=== Batch Size History for {model_name} ===")
        if history:
            print(f"Found {len(history)} changes:\n")
            for i, entry in enumerate(history, 1):
                timestamp = entry.get('timestamp', 'Unknown')[:19]
                old_size = entry.get('old_batch_size', 0)
                new_size = entry.get('new_batch_size', 0)
                change = entry.get('change_amount', 0)
                change_percent = float(entry.get('change_percent', 0))
                reason = entry.get('change_reason', 'unknown')
                session = entry.get('session_id', 'N/A')
                
                change_str = f"{change:+d} ({change_percent:+.1f}%)"
                print(f"{i:3d}. {timestamp}  {old_size:3d} → {new_size:3d}  {change_str:>12}  {reason}")
                print(f"     Session: {session}")
                
                # Show additional context if available
                context_str = entry.get('additional_context', '{}')
                try:
                    import json
                    context = json.loads(context_str)
                    if context:
                        context_parts = []
                        for key, value in context.items():
                            if key in ['consecutive_successes', 'consecutive_failures', 'rate_limit_count']:
                                context_parts.append(f"{key}: {value}")
                            elif key in ['increase_factor', 'decrease_factor', 'weight']:
                                context_parts.append(f"{key}: {value:.2f}")
                        if context_parts:
                            print(f"     Context: {', '.join(context_parts)}")
                except:
                    pass
                print()
        else:
            print("No batch size changes found for this model.")
        
        return history
        
    except Exception as e:
        print(f"[ERROR] Failed to get batch audit history: {e}")
        return []

def get_recent_batch_changes(hours=24, limit=100):
    """Get recent batch size changes across all models."""
    try:
        from shared.batch_audit_logger import BatchAuditLogger
        audit_logger = BatchAuditLogger()
        
        changes = audit_logger.get_recent_changes(hours, limit)
        
        print(f"\n=== Recent Batch Changes (Last {hours} Hours) ===")
        if changes:
            print(f"Found {len(changes)} changes:\n")
            for i, entry in enumerate(changes, 1):
                timestamp = entry.get('timestamp', 'Unknown')[:19]
                model = entry.get('model', 'Unknown')
                old_size = entry.get('old_batch_size', 0)
                new_size = entry.get('new_batch_size', 0)
                change = entry.get('change_amount', 0)
                reason = entry.get('change_reason', 'unknown')
                
                change_str = f"{change:+d}"
                model_short = model[:30] + "..." if len(model) > 30 else model
                print(f"{i:3d}. {timestamp}  {model_short:<33}  {old_size:3d}→{new_size:3d} ({change_str:>4})  {reason}")
        else:
            print("No recent batch size changes found.")
        
        return changes
        
    except Exception as e:
        print(f"[ERROR] Failed to get recent batch changes: {e}")
        return []

def create_batch_audit_table_command():
    """Create the batch audit table."""
    try:
        from shared.batch_audit_logger import create_batch_audit_table
        table = create_batch_audit_table()
        if table:
            print("[SUCCESS] Batch audit table created successfully!")
        else:
            print("[ERROR] Failed to create batch audit table.")
    except Exception as e:
        print(f"[ERROR] Failed to create batch audit table: {e}")

def load_model_config_command(csv_file_path):
    """Load model configurations from CSV into DynamoDB."""
    try:
        from shared.model_config_table import ModelConfigTable
        config_table = ModelConfigTable()
        
        loaded_count = config_table.load_config_from_csv(csv_file_path)
        if loaded_count > 0:
            print(f"[SUCCESS] Loaded {loaded_count} model configurations from {csv_file_path}")
        else:
            print("[ERROR] Failed to load any configurations.")
    except Exception as e:
        print(f"[ERROR] Failed to load model configurations: {e}")

def list_model_configs_command():
    """List all model configurations."""
    try:
        from shared.model_config_table import ModelConfigTable
        config_table = ModelConfigTable()
        
        configs = config_table.list_all_configs()
        
        print("\n=== Model Configurations ===")
        if configs:
            print(f"Found {len(configs)} configurations:\n")
            for i, config in enumerate(configs, 1):
                try:
                    pattern = str(config.get('model_pattern', 'Unknown'))
                    provider = str(config.get('api_provider', 'unknown'))
                    priority = int(config.get('priority', 999))
                    min_batch = int(config.get('min_batch_size', 0))
                    max_batch = int(config.get('max_batch_size', 0))
                    batch_range = str(min_batch) + "-" + str(max_batch)
                    initial = int(config.get('initial_batch_size', 0))
                    weight = float(config.get('weight', 1.0))
                    input_cost = float(config.get('input_cost_per_million_tokens', 0))
                    output_cost = float(config.get('output_cost_per_million_tokens', 0))
                    enabled = config.get('enabled', False)
                    
                    status = "[ENABLED] " if enabled else "[DISABLED]"
                    print("{:3d}. {} {:<35} [{}] Priority: {:3d}".format(i, status, pattern[:35], provider[:10], priority))
                    print("     Batch: {:3d} (range: {}) Weight: {:.1f}".format(initial, batch_range, weight))
                    print("     Cost: ${:.2f} input / ${:.2f} output per million tokens".format(input_cost, output_cost))
                    print()
                except Exception as e:
                    print("[ERROR] Failed to process config {}: {}".format(i, str(e)))
                    print("Config data: {}".format(str(config)))
        else:
            print("No configurations found.")
        
        return configs
        
    except Exception as e:
        print(f"[ERROR] Failed to list model configurations: {e}")
        return []

def test_model_config_command(model_name):
    """Test which configuration a model would match."""
    try:
        from shared.model_config_table import ModelConfigTable
        config_table = ModelConfigTable()
        
        config = config_table.get_config_for_model(model_name)
        
        print(f"\n=== Configuration Test for '{model_name}' ===")
        if config:
            print(f"[SUCCESS] Matched configuration:")
            print(f"  Pattern: {config.get('model_pattern', 'Unknown')}")
            print(f"  Priority: {config.get('priority', 999)}")
            print(f"  Provider: {config.get('api_provider', 'unknown')}")
            print(f"  Initial Batch Size: {config.get('initial_batch_size', 0)}")
            print(f"  Batch Range: {config.get('min_batch_size', 0)}-{config.get('max_batch_size', 0)}")
            print(f"  Weight: {float(config.get('weight', 1.0)):.1f}")
            print(f"  Rate Limit Factor: {float(config.get('rate_limit_factor', 0.75)):.2f}")
            print(f"  Input Cost: ${float(config.get('input_cost_per_million_tokens', 0)):.2f} per million tokens")
            print(f"  Output Cost: ${float(config.get('output_cost_per_million_tokens', 0)):.2f} per million tokens")
            print(f"  Notes: {config.get('notes', 'None')}")
        else:
            print("[ERROR] No matching configuration found.")
            print("This model would use default fallback settings.")
        
        return config
        
    except Exception as e:
        print(f"[ERROR] Failed to test model configuration: {e}")
        return None

def create_model_config_table_command():
    """Create the model configuration table."""
    try:
        from shared.model_config_table import create_model_config_table
        table = create_model_config_table()
        if table:
            print("[SUCCESS] Model configuration table created successfully!")
        else:
            print("[ERROR] Failed to create model configuration table.")
    except Exception as e:
        print(f"[ERROR] Failed to create model configuration table: {e}")

if __name__ == "__main__":
    main() 