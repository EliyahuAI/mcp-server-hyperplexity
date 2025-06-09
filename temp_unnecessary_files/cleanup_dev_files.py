#!/usr/bin/env python3
"""
Cleanup script to move development and testing files to temp_unnecessary_files
"""
import os
import shutil
from pathlib import Path

def move_files_to_temp():
    """Move development files to temp_unnecessary_files directory"""
    
    # Create temp directory if it doesn't exist
    temp_dir = Path("temp_unnecessary_files")
    temp_dir.mkdir(exist_ok=True)
    
    # Files to move (development/testing files)
    files_to_move = [
        "test_current_status.py",
        "verify_field_processing.py", 
        "test_longer_wait.py",
        "progress_log.txt",
        # Result files from testing
        "result_normal_1.zip",
        "result_normal_2.zip", 
        "result_normal_3.zip",
        "result_normal_4.zip",
        "result_check_1.zip",
        "result_check_2.zip",
        "result_check_3.zip",
        "result_check_4.zip",
        "placeholder_1.zip",
        "placeholder_2.zip",
        "placeholder_3.zip",
        "placeholder_4.zip",
        # Old test files
        "test_preview_mode.py",
        "test_normal_mode.py",
        "cleanup_dev_files.py"  # Move this script itself after running
    ]
    
    moved_files = []
    not_found = []
    
    for file_name in files_to_move:
        file_path = Path(file_name)
        if file_path.exists():
            try:
                dest_path = temp_dir / file_name
                shutil.move(str(file_path), str(dest_path))
                moved_files.append(file_name)
                print(f"✅ Moved: {file_name}")
            except Exception as e:
                print(f"❌ Error moving {file_name}: {e}")
        else:
            not_found.append(file_name)
    
    print(f"\n📊 CLEANUP SUMMARY:")
    print(f"✅ Files moved: {len(moved_files)}")
    print(f"⚠️  Files not found: {len(not_found)}")
    
    if moved_files:
        print(f"\n📁 Moved to temp_unnecessary_files/:")
        for file in moved_files:
            print(f"   - {file}")
    
    if not_found:
        print(f"\n⚠️  Files not found (already moved or never created):")
        for file in not_found:
            print(f"   - {file}")

if __name__ == "__main__":
    print("🧹 CLEANING UP DEVELOPMENT FILES")
    print("=" * 50)
    move_files_to_temp()
    print(f"\n🎉 Cleanup complete!") 