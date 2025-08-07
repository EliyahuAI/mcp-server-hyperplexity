#!/usr/bin/env python3
"""
Quick script to update the config package with the latest ai_api_client.py
"""
import shutil
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
CONFIG_PACKAGE_DIR = SCRIPT_DIR / "config_package"

def update_config_package():
    """Update config package with latest files from src."""
    
    # Core files to update
    files_to_update = [
        "ai_api_client.py",
        "config_lambda_function.py",
        "perplexity_schema.py",
        "shared_table_parser.py",
        "config_validator.py",
        "column_config_schema.json"
    ]
    
    # Config generator files from lambdas/config
    config_generator_files = [
        "config_generator_conversational.py",
        "config_generator_step1.py", 
        "config_generator_step2_enhanced.py"
    ]
    
    # Additional files from specific locations
    additional_files = [
        ("src/lambdas/config/ai_generation_schema.json", "ai_generation_schema.json")
    ]
    
    print("Updating config package...")
    
    # Copy core files from src/ and src/shared/
    for file_name in files_to_update:
        # Try src/ first, then src/shared/
        src_file = SRC_DIR / file_name
        if not src_file.exists():
            src_file = SRC_DIR / "shared" / file_name
        
        dest_file = CONFIG_PACKAGE_DIR / file_name
        
        if src_file.exists():
            shutil.copy(src_file, dest_file)
            print(f"Updated: {file_name}")
        else:
            print(f"Warning: {file_name} not found in src or src/shared")
    
    # Copy config generator files from src/lambdas/config/
    config_lambda_dir = SRC_DIR / "lambdas" / "config"
    for file_name in config_generator_files:
        src_file = config_lambda_dir / file_name
        dest_file = CONFIG_PACKAGE_DIR / file_name
        
        if src_file.exists():
            shutil.copy(src_file, dest_file)
            print(f"Updated: {file_name}")
        else:
            print(f"Warning: {file_name} not found in lambdas/config")
    
    # Copy additional files
    for src_path, dest_name in additional_files:
        src_file = PROJECT_DIR / src_path
        dest_file = CONFIG_PACKAGE_DIR / dest_name
        
        if src_file.exists():
            shutil.copy(src_file, dest_file)
            print(f"Updated: {dest_name}")
        else:
            print(f"Warning: {src_path} not found")
    
    print("\nConfig package updated successfully!")
    print(f"Package location: {CONFIG_PACKAGE_DIR}")

if __name__ == "__main__":
    update_config_package()