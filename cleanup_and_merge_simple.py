#!/usr/bin/env python3
"""
Simple cleanup script - only moves test files, then commits and merges
"""
import os
import shutil
import subprocess
import sys

def run_command(cmd, check=True):
    """Run a shell command and return the output"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

def move_test_files():
    """Move only test files to temp directory"""
    temp_dir = "temp_unnecessary_files"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created directory: {temp_dir}")
    
    # Only move specific test files that we know exist
    test_files = [
        "test_sequential_preview.py",
        "test_sequential_integration.py",
        "test_full_validation.py",
        "cleanup_and_merge.py"  # Also move the previous cleanup script
    ]
    
    moved_files = []
    for file in test_files:
        if os.path.exists(file):
            dest = os.path.join(temp_dir, file)
            try:
                shutil.move(file, dest)
                moved_files.append(file)
                print(f"Moved: {file} -> {dest}")
            except Exception as e:
                print(f"Could not move {file}: {e}")
    
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
    
    # Check git status
    print("\nChecking git status...")
    run_command("git status", check=False)
    
    # Add only source code changes (not deployment packages)
    print("\nAdding source code changes...")
    run_command("git add src/*.py")
    run_command("git add deployment/*.py")
    run_command("git add *.md")
    run_command("git add .gitignore")
    run_command("git add agent_logs.md")
    
    # Check what's staged
    result = run_command("git status --porcelain", check=False)
    if "M " in result.stdout or "A " in result.stdout or "D " in result.stdout:
        print("\nStaged changes:")
        run_command("git diff --cached --name-only", check=False)
        
        # Commit with descriptive message
        commit_msg = "feat: Fixed API call counting and processing time tracking\n\n" \
                     "- Fixed API call counting bug (was nested in token usage check)\n" \
                     "- Fixed processing time extraction from validator metadata\n" \
                     "- Fixed session ID parsing for async preview\n" \
                     "- All 3 preview rows now sent in one batch\n" \
                     "- Cleaned up test files"
        
        run_command(f'git commit -m "{commit_msg}"')
        print("Changes committed successfully")
    else:
        print("No changes to commit")
    
    # Push current branch
    print(f"\nPushing {current_branch} to origin...")
    result = run_command(f"git push origin {current_branch}", check=False)
    if result.returncode != 0:
        print("Push failed, trying to set upstream...")
        run_command(f"git push -u origin {current_branch}")
    
    # Ask user before merging to master
    if current_branch != "master" and current_branch != "main":
        response = input(f"\nMerge {current_branch} into master? (y/n): ")
        if response.lower() == 'y':
            # Checkout master
            print("\nSwitching to master branch...")
            run_command("git checkout master")
            
            # Pull latest master
            print("Pulling latest master...")
            run_command("git pull origin master", check=False)
            
            # Merge feature branch
            print(f"Merging {current_branch} into master...")
            merge_msg = f"Merge branch '{current_branch}': Cost and time tracking enhancements"
            run_command(f'git merge {current_branch} --no-ff -m "{merge_msg}"')
            
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
    print("=== Simple Cleanup and Git Operations Script ===\n")
    
    # Step 1: Clean up test files only
    print("Step 1: Moving test files...")
    moved_files = move_test_files()
    print(f"Moved {len(moved_files)} test files to temp_unnecessary_files\n")
    
    # Step 2: Git operations
    print("Step 2: Git operations...")
    git_operations()
    
    print("\n✅ All operations completed successfully!")

if __name__ == "__main__":
    main() 