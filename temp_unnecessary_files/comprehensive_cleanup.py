#!/usr/bin/env python3
"""
Comprehensive cleanup script to move all development and testing files to temp_unnecessary_files
"""
import os
import shutil
from pathlib import Path
import glob

def move_files_to_temp():
    """Move all development/testing files to temp_unnecessary_files directory"""
    
    # Create temp directory if it doesn't exist
    temp_dir = Path("temp_unnecessary_files")
    temp_dir.mkdir(exist_ok=True)
    
    # Individual files to move
    files_to_move = [
        "check_results.py",
        "debug_download.zip", 
        "debug_normal_mode.py",
        "debug_validator_response.py",
        "enhanced_results.zip",
        "example_processed_result.xlsx",
        "fix_test_data.py",
        "full_validation_results.zip",
        "immediate_download.zip",
        "show_outputs.py",
        "test_download.zip",
        "test_result.zip", 
        "updated_download_5s.zip",
        "comprehensive_cleanup.py"  # Move this script itself after running
    ]
    
    # Directories to move
    dirs_to_move = [
        "deployment/interface_package",
        "extracted_result",
        "test_events",
        "tables"
    ]
    
    # Deployment artifacts to move
    deployment_files = [
        "deployment/interface_lambda_package.zip"
    ]
    
    moved_items = []
    not_found = []
    
    print("🧹 COMPREHENSIVE CLEANUP")
    print("=" * 50)
    
    # Move individual files
    print("📄 Moving files...")
    for file_name in files_to_move + deployment_files:
        file_path = Path(file_name)
        if file_path.exists():
            try:
                # Create nested directory structure if needed
                dest_path = temp_dir / file_name
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                shutil.move(str(file_path), str(dest_path))
                moved_items.append(file_name)
                print(f"✅ Moved: {file_name}")
            except Exception as e:
                print(f"❌ Error moving {file_name}: {e}")
        else:
            not_found.append(file_name)
    
    # Move directories
    print("\n📁 Moving directories...")
    for dir_name in dirs_to_move:
        dir_path = Path(dir_name)
        if dir_path.exists() and dir_path.is_dir():
            try:
                dest_path = temp_dir / dir_name
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                shutil.move(str(dir_path), str(dest_path))
                moved_items.append(dir_name)
                print(f"✅ Moved directory: {dir_name}")
            except Exception as e:
                print(f"❌ Error moving directory {dir_name}: {e}")
        else:
            not_found.append(dir_name)
    
    # Clean up any remaining .zip files in root
    print("\n🗜️  Cleaning up remaining ZIP files...")
    zip_files = glob.glob("*.zip")
    for zip_file in zip_files:
        if not zip_file.startswith("temp_"):  # Don't move temp files
            try:
                dest_path = temp_dir / zip_file
                shutil.move(zip_file, str(dest_path))
                moved_items.append(zip_file)
                print(f"✅ Moved ZIP: {zip_file}")
            except Exception as e:
                print(f"❌ Error moving ZIP {zip_file}: {e}")
    
    # Clean up any remaining .py test/debug files
    print("\n🐍 Cleaning up remaining Python test files...")
    py_files = glob.glob("*.py")
    test_debug_patterns = [
        "test_", "debug_", "check_", "fix_", "show_", "temp_", "verify_"
    ]
    
    for py_file in py_files:
        if any(py_file.startswith(pattern) for pattern in test_debug_patterns):
            try:
                dest_path = temp_dir / py_file
                shutil.move(py_file, str(dest_path))
                moved_items.append(py_file)
                print(f"✅ Moved Python test: {py_file}")
            except Exception as e:
                print(f"❌ Error moving Python test {py_file}: {e}")
    
    print(f"\n📊 CLEANUP SUMMARY:")
    print(f"✅ Items moved: {len(moved_items)}")
    print(f"⚠️  Items not found: {len(not_found)}")
    
    if moved_items:
        print(f"\n📁 Moved to temp_unnecessary_files/:")
        for item in sorted(moved_items):
            print(f"   - {item}")

def check_remaining_clutter():
    """Check what's left in the root directory"""
    print(f"\n🔍 CHECKING REMAINING FILES:")
    
    # List all files in root (excluding essential ones)
    essential_patterns = [
        "src/", "deployment/create_", "test_cases/", "temp_unnecessary_files/", 
        ".git", "README", "requirements", "interface-requirements.md", ".py"
    ]
    
    all_items = list(Path(".").iterdir())
    potentially_clutter = []
    
    for item in all_items:
        if item.name.startswith("."):
            continue  # Skip hidden files
        
        is_essential = False
        for pattern in essential_patterns:
            if pattern in str(item) or item.name.startswith(pattern.replace("/", "")):
                is_essential = True
                break
        
        if not is_essential:
            potentially_clutter.append(item)
    
    if potentially_clutter:
        print("⚠️  Potentially remaining clutter:")
        for item in sorted(potentially_clutter):
            print(f"   - {item}")
    else:
        print("✅ No obvious clutter remaining!")

if __name__ == "__main__":
    move_files_to_temp()
    check_remaining_clutter()
    print(f"\n🎉 Comprehensive cleanup complete!") 