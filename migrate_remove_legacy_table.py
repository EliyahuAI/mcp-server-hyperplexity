#!/usr/bin/env python3
"""
Migration Script: Remove Legacy Call-Tracking Table Usage

This script removes all references to the legacy perplexity-validator-call-tracking
table and ensures all tracking is done through the modern perplexity-validator-runs table.

Steps:
1. Remove function calls from active code
2. Remove/comment out function definitions
3. Update imports to avoid importing legacy functions
4. Clear the legacy table (optional)
"""

import os
import re
import sys
from pathlib import Path

def find_and_replace_in_file(file_path, patterns_to_remove, patterns_to_replace):
    """Remove legacy tracking calls from a file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        modified = False
        
        # Remove specific function calls
        for pattern in patterns_to_remove:
            new_content = re.sub(pattern, '', content, flags=re.MULTILINE | re.DOTALL)
            if new_content != content:
                content = new_content
                modified = True
                print(f"  [REMOVED] Pattern: {pattern[:50]}...")
        
        # Replace specific patterns
        for old_pattern, new_pattern in patterns_to_replace:
            new_content = re.sub(old_pattern, new_pattern, content, flags=re.MULTILINE | re.DOTALL)
            if new_content != content:
                content = new_content
                modified = True
                print(f"  [REPLACED] {old_pattern[:30]}... -> {new_pattern[:30]}...")
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[SUCCESS] Modified: {file_path}")
            return True
        else:
            print(f"[SKIP] No changes needed: {file_path}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to process {file_path}: {e}")
        return False

def migrate_process_excel():
    """Remove legacy tracking from process_excel.py"""
    file_path = "src/lambdas/interface/actions/process_excel.py"
    print(f"\n=== Migrating {file_path} ===")
    
    patterns_to_remove = [
        r'track_validation_call\([^)]+\)',  # Remove track_validation_call calls
    ]
    
    patterns_to_replace = [
        # Remove import
        (r'from shared\.dynamodb_schemas import[^,]*track_validation_call[^,]*,?', ''),
        # Clean up any remaining comma issues in imports
        (r'from shared\.dynamodb_schemas import\s*,', 'from shared.dynamodb_schemas import'),
        (r'from shared\.dynamodb_schemas import([^,]+),\s*,', r'from shared.dynamodb_schemas import\1'),
    ]
    
    return find_and_replace_in_file(file_path, patterns_to_remove, patterns_to_replace)

def migrate_process_excel_unified():
    """Remove legacy tracking from process_excel_unified.py"""
    file_path = "src/lambdas/interface/actions/process_excel_unified.py"
    print(f"\n=== Migrating {file_path} ===")
    
    patterns_to_remove = [
        r'track_validation_call\([^)]+\)',  # Remove track_validation_call calls
        # Remove the entire fallback import block
        r'try:\s*from shared\.dynamodb_schemas import[^}]+except[^}]+track_validation_call\s*=\s*lambda[^}]+',
    ]
    
    patterns_to_replace = [
        # Remove import from the main import statement
        (r'from shared\.dynamodb_schemas import[^,]*track_validation_call[^,]*,?', ''),
    ]
    
    return find_and_replace_in_file(file_path, patterns_to_remove, patterns_to_replace)

def migrate_background_handler():
    """Remove legacy tracking from background_handler.py"""
    file_path = "src/lambdas/interface/handlers/background_handler.py"
    print(f"\n=== Migrating {file_path} ===")
    
    patterns_to_remove = [
        r'track_api_usage_detailed\([^)]+\)',      # Remove API usage tracking
        r'track_email_delivery\([^)]+\)',          # Remove email delivery tracking  
        r'track_preview_cost\([^)]+\)',            # Remove preview cost tracking
        # Remove the entire fallback import block
        r'try:\s*from shared\.dynamodb_schemas import[^}]+except[^}]+update_processing_metrics\s*=\s*lambda[^}]+',
    ]
    
    patterns_to_replace = [
        # Remove imports
        (r'from shared\.dynamodb_schemas import[^,]*track_api_usage_detailed[^,]*,?', ''),
        (r'from shared\.dynamodb_schemas import[^,]*track_email_delivery[^,]*,?', ''),
        (r'from shared\.dynamodb_schemas import[^,]*track_preview_cost[^,]*,?', ''),
        (r'from shared\.dynamodb_schemas import[^,]*update_processing_metrics[^,]*,?', ''),
    ]
    
    return find_and_replace_in_file(file_path, patterns_to_remove, patterns_to_replace)

def migrate_generate_config_unified():
    """Remove legacy tracking from generate_config_unified.py"""
    file_path = "src/lambdas/interface/actions/generate_config_unified.py"
    print(f"\n=== Migrating {file_path} ===")
    
    patterns_to_replace = [
        # Remove the unused import
        (r'from shared\.dynamodb_schemas import[^,]*update_processing_metrics[^,]*,?', ''),
    ]
    
    return find_and_replace_in_file(file_path, [], patterns_to_replace)

def migrate_manage_dynamodb_tables():
    """Update management script to remove legacy table references"""
    file_path = "src/manage_dynamodb_tables.py"
    print(f"\n=== Migrating {file_path} ===")
    
    patterns_to_replace = [
        # Update the summary function to skip legacy table
        (r'for table_name in \[USER_VALIDATION_TABLE, USER_TRACKING_TABLE, CALL_TRACKING_TABLE\]:', 
         'for table_name in [USER_VALIDATION_TABLE, USER_TRACKING_TABLE, RUNS_TABLE]:'),
        # Update export list to remove legacy table
        (r'tables_to_export = \[[^\]]*CALL_TRACKING_TABLE[^\]]*\]',
         '''tables_to_export = [
        USER_VALIDATION_TABLE, USER_TRACKING_TABLE, RUNS_TABLE,
        ACCOUNT_TRANSACTIONS_TABLE, DOMAIN_MULTIPLIERS_TABLE,
        TOKEN_USAGE_TABLE, WS_CONNECTIONS_TABLE
    ]'''),
    ]
    
    return find_and_replace_in_file(file_path, [], patterns_to_replace)

def comment_out_legacy_functions():
    """Comment out legacy tracking functions in dynamodb_schemas.py"""
    file_path = "src/shared/dynamodb_schemas.py"
    print(f"\n=== Commenting out legacy functions in {file_path} ===")
    
    # Functions to comment out
    functions_to_disable = [
        'track_validation_call',
        'update_call_status',
        'update_processing_metrics', 
        'track_api_usage_detailed',
        'track_email_delivery',
        'track_lambda_performance',
        'track_preview_cost',
        'track_abandoned_session',
        'get_call_record',
        'get_call_analytics',
        'create_call_tracking_table',
        'get_call_tracking_schema'
    ]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        modified = False
        
        for func_name in functions_to_disable:
            # Pattern to match function definition and its entire body
            pattern = rf'^(def {func_name}\([^:]*\):.*?)(?=^def|\Z)'
            
            def replace_func(match):
                func_content = match.group(1)
                # Add comment header and indent all lines
                commented = f'''# LEGACY FUNCTION - DISABLED
# This function used the legacy call-tracking table and has been disabled
# in favor of the modern perplexity-validator-runs table tracking.
# def {func_name}(...):
#     pass
'''
                return commented
            
            new_content = re.sub(pattern, replace_func, content, flags=re.MULTILINE | re.DOTALL)
            if new_content != content:
                content = new_content
                modified = True
                print(f"  [DISABLED] Function: {func_name}")
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[SUCCESS] Disabled legacy functions in: {file_path}")
            return True
        else:
            print(f"[SKIP] No functions to disable in: {file_path}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to process {file_path}: {e}")
        return False

def main():
    """Run the migration"""
    print("=" * 60)
    print("  MIGRATION: Remove Legacy Call-Tracking Table Usage")
    print("=" * 60)
    
    # Change to project directory (handle both WSL and Windows paths)
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    changes_made = []
    
    # Migrate each file
    if migrate_process_excel():
        changes_made.append("process_excel.py")
    
    if migrate_process_excel_unified():
        changes_made.append("process_excel_unified.py")
        
    if migrate_background_handler():
        changes_made.append("background_handler.py")
        
    if migrate_generate_config_unified():
        changes_made.append("generate_config_unified.py")
        
    if migrate_manage_dynamodb_tables():
        changes_made.append("manage_dynamodb_tables.py")
    
    if comment_out_legacy_functions():
        changes_made.append("dynamodb_schemas.py")
    
    print("\n" + "=" * 60)
    print("  MIGRATION SUMMARY")
    print("=" * 60)
    
    if changes_made:
        print("[SUCCESS] Migration completed successfully!")
        print(f"[INFO] Modified {len(changes_made)} files:")
        for file in changes_made:
            print(f"  - {file}")
        print("\n[NEXT STEPS]:")
        print("1. Test the system to ensure tracking still works")
        print("2. Deploy changes to remove legacy table dependencies")  
        print("3. Optional: Clear the legacy call-tracking table")
        print("4. Update documentation to reflect the changes")
    else:
        print("[INFO] No changes were needed - system already clean")
    
    print("=" * 60)

if __name__ == "__main__":
    main()