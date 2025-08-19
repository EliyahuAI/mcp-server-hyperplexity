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
        return False

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
            cost = cost_estimates.get('preview_cost', 0.0)
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
        total_cost = sum(float(item.get('preview_data', {}).get('cost_estimates', {}).get('preview_cost', 0)) for item in items)
        
        print(f"[STATS] Completed: {completed_sessions}, Failed: {failed_sessions}, Total Cost: ${total_cost:.3f}")
        
        return items
        
    except Exception as e:
        print(f"Error getting recent runs: {e}")
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
        
        print(f"[SCANNING] Scanning table {table_name}...")
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        if not items:
            print(f"[ERROR] No items found in table {table_name}")
            return None
        
        print(f"[INFO] Found {len(items)} items to export")
        
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
        
        print(f"[SUCCESS] Successfully exported {len(items)} items to {filepath}")
        print(f"[INFO] Columns: {', '.join(fieldnames)}")
        return filepath
        
    except Exception as e:
        print(f"[ERROR] Error exporting table {table_name} to CSV: {e}")
        return None

def export_all_tables_to_csv(output_dir="exports", limit=None):
    """Export all perplexity-validator tables to CSV files"""
    tables_to_export = [
        USER_VALIDATION_TABLE, USER_TRACKING_TABLE, RUNS_TABLE,
        ACCOUNT_TRANSACTIONS_TABLE, DOMAIN_MULTIPLIERS_TABLE,
        TOKEN_USAGE_TABLE, WS_CONNECTIONS_TABLE
    ]
    exported_files = []
    
    print(f"[EXPORTING] Starting export of all DynamoDB tables to {output_dir}/")
    print("=" * 60)
    
    for table_name in tables_to_export:
        print(f"\n[EXPORTING] Exporting {table_name}...")
        filepath = export_table_to_csv(table_name, output_dir, limit)
        if filepath:
            exported_files.append(filepath)
    
    print("\n" + "=" * 60)
    print(f"[SUCCESS] Export complete! {len(exported_files)} files created:")
    for filepath in exported_files:
        file_size = os.path.getsize(filepath) / 1024  # KB
        print(f"   [FILE] {filepath} ({file_size:.1f} KB)")
    
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
    python manage_dynamodb_tables.py calls                   # Show recent call tracking (legacy)
    python manage_dynamodb_tables.py recent [limit]          # Show recent validation runs (rich format)
    python manage_dynamodb_tables.py recent-calls [limit]    # Same as recent
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

Examples:
    python manage_dynamodb_tables.py validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py delete-validation eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py clear perplexity-validator-user-validation
    python manage_dynamodb_tables.py export-csv perplexity-validator-user-tracking
    python manage_dynamodb_tables.py export-all-csv 100
    python manage_dynamodb_tables.py export-user-csv eliyahu@eliyahu.ai
    
    python manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py add-balance eliyahu@eliyahu.ai 25.50
    python manage_dynamodb_tables.py list-transactions eliyahu@eliyahu.ai
    python manage_dynamodb_tables.py set-multiplier eliyahu.ai 3.0
    python manage_dynamodb_tables.py get-multiplier eliyahu.ai
    python manage_dynamodb_tables.py set-global-multiplier 5.0
    python manage_dynamodb_tables.py create-account-tables
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
    
    elif command == "recent" or command == "recent-calls":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        get_recent_runs_rich_table(limit)
    
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
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'python manage_dynamodb_tables.py' for help.")

if __name__ == "__main__":
    main() 