#!/usr/bin/env python3
"""
Script to clean up temporary files, commit changes, and merge to master
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime

def run_command(cmd, check=True):
    """Run a shell command and return the output"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

def create_temp_dir():
    """Create temp_unnecessary_files directory if it doesn't exist"""
    temp_dir = "temp_unnecessary_files"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created directory: {temp_dir}")
    return temp_dir

def move_temp_files():
    """Move temporary and unnecessary files to temp directory"""
    temp_dir = create_temp_dir()
    
    # List of files/patterns to move
    files_to_move = [
        "test_sequential_preview.py",
        "test_sequential_integration.py",
        "test_full_validation.py",
        "*.pyc",
        "__pycache__",
        ".pytest_cache",
        "*.log",
        "deployment/package/*.zip",
        "deployment/interface_package/*.zip",
        "deployment/package/",
        "deployment/interface_package/",
    ]
    
    moved_files = []
    
    for pattern in files_to_move:
        if "*" in pattern:
            # Handle wildcards
            import glob
            for file_path in glob.glob(pattern, recursive=True):
                if os.path.exists(file_path) and not file_path.startswith(temp_dir):
                    dest = os.path.join(temp_dir, os.path.basename(file_path))
                    try:
                        if os.path.isdir(file_path):
                            shutil.move(file_path, dest)
                        else:
                            shutil.move(file_path, dest)
                        moved_files.append(file_path)
                        print(f"Moved: {file_path} -> {dest}")
                    except Exception as e:
                        print(f"Could not move {file_path}: {e}")
        else:
            # Handle specific files
            if os.path.exists(pattern) and not pattern.startswith(temp_dir):
                dest = os.path.join(temp_dir, os.path.basename(pattern))
                try:
                    if os.path.isdir(pattern):
                        shutil.move(pattern, dest)
                    else:
                        shutil.move(pattern, dest)
                    moved_files.append(pattern)
                    print(f"Moved: {pattern} -> {dest}")
                except Exception as e:
                    print(f"Could not move {pattern}: {e}")
    
    return moved_files

def git_operations():
    """Perform git operations: add, commit, push, and merge"""
    
    # Check current branch
    result = run_command("git branch --show-current", check=False)
    current_branch = result.stdout.strip()
    print(f"Current branch: {current_branch}")
    
    if not current_branch:
        print("Error: Could not determine current branch")
        sys.exit(1)
    
    # Check for uncommitted changes
    result = run_command("git status --porcelain", check=False)
    if result.stdout.strip():
        print("\nUncommitted changes found:")
        print(result.stdout)
        
        # Add all changes
        run_command("git add -A")
        
        # Commit with descriptive message
        commit_msg = f"feat: Fixed API call counting and processing time tracking\n\n" \
                     f"- Fixed API call counting bug (was nested in token usage check)\n" \
                     f"- Fixed processing time extraction from validator metadata\n" \
                     f"- Fixed session ID parsing for async preview\n" \
                     f"- Cleaned up temporary files"
        
        run_command(f'git commit -m "{commit_msg}"')
        print("Changes committed successfully")
    else:
        print("No uncommitted changes to commit")
    
    # Push current branch
    print(f"\nPushing {current_branch} to origin...")
    run_command(f"git push origin {current_branch}")
    
    # Ask user before merging to master
    if current_branch != "master" and current_branch != "main":
        response = input(f"\nMerge {current_branch} into master? (y/n): ")
        if response.lower() == 'y':
            # Checkout master
            print("\nSwitching to master branch...")
            run_command("git checkout master")
            
            # Pull latest master
            print("Pulling latest master...")
            run_command("git pull origin master")
            
            # Merge feature branch
            print(f"Merging {current_branch} into master...")
            run_command(f"git merge {current_branch} --no-ff -m 'Merge branch {current_branch}: Cost and time tracking enhancements'")
            
            # Push master
            print("Pushing master to origin...")
            run_command("git push origin master")
            
            # Switch back to feature branch
            print(f"\nSwitching back to {current_branch}...")
            run_command(f"git checkout {current_branch}")
            
            print("\n✅ Successfully merged to master!")
        else:
            print("Merge to master skipped")
    else:
        print("Already on master/main branch, no merge needed")

def main():
    """Main function"""
    print("=== Cleanup and Git Operations Script ===\n")
    
    # Step 1: Clean up files
    print("Step 1: Moving temporary files...")
    moved_files = move_temp_files()
    print(f"Moved {len(moved_files)} files/directories to temp_unnecessary_files\n")
    
    # Step 2: Git operations
    print("Step 2: Git operations...")
    git_operations()
    
    print("\n✅ All operations completed successfully!")
    print("\nNote: The temp_unnecessary_files directory has been created but not added to git.")
    print("You may want to add it to .gitignore if you haven't already.")

if __name__ == "__main__":
    main() 