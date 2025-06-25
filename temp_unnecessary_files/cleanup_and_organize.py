#!/usr/bin/env python3
"""
Clean up and organize project files after fixing Excel corruption issue.
"""

import os
import shutil
from pathlib import Path

def cleanup_project():
    """Move unnecessary debug files to temp folder."""
    
    # Create temp_unnecessary_files directory if it doesn't exist
    temp_dir = Path("temp_unnecessary_files")
    temp_dir.mkdir(exist_ok=True)
    
    # List of files to move
    debug_files = [
        "debug_excel_xml.py",
        "analyze_excel_corruption.py",
        "compare_excel_files.py",
        "debug_excel_content.py",
        "clean_lambda_permissions.py",
        "debug_excel_specific_row.py",
        "temp_excel_xml_debug.log",
        "detailed_comparison.txt",
        "lambda_policy.json",
        # Excel test files
        "minimal_no_options.xlsx",
        "with_strings_to_urls_false.xlsx",
        "with_all_options.xlsx",
        "with_constant_memory.xlsx",
        "validation_results_enhanced.xlsx",
        "validation_results_enhanced2.xlsx",
        "validation_results.csv"
    ]
    
    moved_files = []
    kept_files = []
    
    for file in debug_files:
        if os.path.exists(file):
            try:
                shutil.move(file, temp_dir / file)
                moved_files.append(file)
                print(f"✓ Moved: {file}")
            except Exception as e:
                print(f"✗ Error moving {file}: {e}")
        else:
            # File doesn't exist, skip
            pass
    
    print(f"\n📁 Moved {len(moved_files)} files to {temp_dir}/")
    
    # List important files that were kept
    important_files = [
        "src/interface_lambda_function.py",
        "src/lambda_test_json_clean.py", 
        "src/row_key_utils.py",
        "deployment/create_interface_package.py"
    ]
    
    print("\n📌 Important files kept in place:")
    for file in important_files:
        if os.path.exists(file):
            print(f"  ✓ {file}")
    
    return moved_files

if __name__ == "__main__":
    print("🧹 Cleaning up project files...\n")
    cleanup_project()
    print("\n✅ Cleanup complete!") 