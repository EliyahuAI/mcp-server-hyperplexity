#!/usr/bin/env python3
"""
Project cleanup script to organize files and prepare for git push.
Moves unnecessary files to temp_unnecessary_files directory.
"""
import os
import shutil
from pathlib import Path
import re

# Define project root
PROJECT_ROOT = Path(__file__).parent
TEMP_DIR = PROJECT_ROOT / "temp_unnecessary_files"

# Files to keep (important files)
KEEP_PATTERNS = [
    # Core source files
    r"^src/(lambda_function|interface_lambda_function|schema_validator|schema_validator_simplified|"
    r"perplexity_schema|prompt_loader|row_key_utils|excel_processor|excel_batch_processor|"
    r"lambda_test_json_clean|email_sender|url_extractor|excel_history_manager|"
    r"batch_validate|excel_validator_cli|validator)\.py$",
    
    # Configuration files
    r"^src/(prompts\.yml|sample_config\.yml)$",
    r"^requirements.*\.txt$",
    r"^\.gitignore$",
    r"^README.*\.md$",
    
    # Deployment files
    r"^deployment/create_package\.py$",
    r"^deployment/create_interface_package\.py$",
    r"^deployment/.*\.json$",  # Keep deployment configs
    
    # Keep this cleanup script
    r"^cleanup_project\.py$",
    
    # Local execution files
    r"^batch_validate\.py$",
    
    # Test events (might be useful)
    r"^test_events/.*\.json$",
]

# Files to move (unnecessary files)
MOVE_PATTERNS = [
    # Test and debug scripts
    r".*test.*\.py$",
    r".*debug.*\.py$",
    r".*diagnose.*\.py$",
    r".*quick.*\.py$",
    r".*show.*\.py$",
    r".*check.*\.py$",
    r".*send.*\.py$",
    
    # Example and demo files
    r".*example.*",
    r".*demo.*",
    r".*sample.*\.xlsx$",
    r".*sample.*\.json$",
    
    # Old documentation (as requested)
    r"^CLEAN_ROW_KEY_HISTORY_SOLUTION\.md$",
    r"^ROW_KEY_AND_VALIDATION_HISTORY_REFERENCE\.md$",
    r"^interface-requirements\.md$",
    r"^QUICK_START\.md$",
    r"^temp_validation_fixes_tracker\.md$",
    
    # Jupyter notebooks
    r".*\.ipynb$",
    
    # Log files
    r".*\.log$",
    r".*_log\.txt$",
    r"progress_log\.txt$",
    
    # Cache and temporary files
    r".*\.pyc$",
    r"__pycache__",
    r".*\.cache$",
    
    # Build artifacts
    r"^deployment/package/?",
    r"^deployment/interface_package/?",
    r"^deployment/.*\.zip$",
    
    # JSON output files
    r".*_output.*\.json$",
    r".*_result.*\.json$",
    r".*_response.*\.json$",
    r"lambda_.*\.json$",
    
    # Old scripts
    r"^json_to_excel\.py$",
    r"^excel_test\.py$",
    
    # Directories to move
    r"^examples/",
    r"^tables/",
    r"^test_cases/",
    r"^prompts/",  # Old prompts directory
    
    # Additional src files to move (only non-essential ones)
    r"^src/column_config_template\.json$",
    r"^src/excel_history_processor\.py$",  # Keep excel_history_manager.py
    r"^src/multiplex_parser\.py$",
    r"^src/README_EXCEL_VALIDATOR\.md$",
    r"^src/schema_validator_enhanced\.py$",  # Keep simplified version
]

# Files to delete (build artifacts)
DELETE_PATTERNS = [
    r"^deployment/lambda_package\.zip$",
    r"^deployment/interface_lambda_package\.zip$",
    r"^deployment/package/?",
    r"^deployment/interface_package/?",
    r"\.pyc$",
    r"__pycache__",
]

def should_keep(filepath):
    """Check if file should be kept."""
    path_str = str(filepath.relative_to(PROJECT_ROOT)).replace('\\', '/')
    
    for pattern in KEEP_PATTERNS:
        if re.match(pattern, path_str):
            return True
    return False

def should_move(filepath):
    """Check if file should be moved."""
    path_str = str(filepath.relative_to(PROJECT_ROOT)).replace('\\', '/')
    
    # Don't move if it should be kept
    if should_keep(filepath):
        return False
    
    for pattern in MOVE_PATTERNS:
        if re.search(pattern, path_str):
            return True
    return False

def should_delete(filepath):
    """Check if file should be deleted."""
    path_str = str(filepath.relative_to(PROJECT_ROOT)).replace('\\', '/')
    
    for pattern in DELETE_PATTERNS:
        if re.search(pattern, path_str):
            return True
    return False

def clean_project():
    """Main cleanup function."""
    # Create temp directory
    TEMP_DIR.mkdir(exist_ok=True)
    
    moved_files = []
    deleted_files = []
    kept_files = []
    
    # Walk through all files
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip the temp directory itself
        if TEMP_DIR in Path(root).parents or Path(root) == TEMP_DIR:
            continue
            
        # Skip .git directory
        if '.git' in root:
            continue
        
        for filename in files:
            filepath = Path(root) / filename
            
            if should_delete(filepath):
                # Delete build artifacts
                try:
                    filepath.unlink()
                    deleted_files.append(filepath)
                    print(f"Deleted: {filepath.relative_to(PROJECT_ROOT)}")
                except Exception as e:
                    print(f"Error deleting {filepath}: {e}")
                    
            elif should_move(filepath):
                # Move to temp directory
                try:
                    # Create subdirectory structure in temp
                    rel_path = filepath.relative_to(PROJECT_ROOT)
                    temp_path = TEMP_DIR / rel_path
                    temp_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    shutil.move(str(filepath), str(temp_path))
                    moved_files.append(rel_path)
                    print(f"Moved: {rel_path}")
                except Exception as e:
                    print(f"Error moving {filepath}: {e}")
            
            elif should_keep(filepath):
                kept_files.append(filepath.relative_to(PROJECT_ROOT))
        
        # Handle directories
        for dirname in dirs[:]:  # Use slice to modify list during iteration
            dirpath = Path(root) / dirname
            
            if should_delete(dirpath):
                try:
                    shutil.rmtree(dirpath)
                    deleted_files.append(dirpath)
                    dirs.remove(dirname)  # Don't descend into deleted directory
                    print(f"Deleted directory: {dirpath.relative_to(PROJECT_ROOT)}")
                except Exception as e:
                    print(f"Error deleting directory {dirpath}: {e}")
    
    # Summary
    print(f"\n=== Cleanup Summary ===")
    print(f"Files moved: {len(moved_files)}")
    print(f"Files deleted: {len(deleted_files)}")
    print(f"Files kept: {len(kept_files)}")
    
    # Create/update .gitignore
    create_gitignore()
    
    return moved_files, deleted_files, kept_files

def create_gitignore():
    """Create or update .gitignore file."""
    gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# PyCharm
.idea/

# VS Code
.vscode/

# Jupyter Notebook
.ipynb_checkpoints
*.ipynb

# Environment
.env
.venv

# AWS Lambda packages
deployment/package/
deployment/interface_package/
deployment/*.zip
*.zip

# Logs
*.log
*_log.txt
progress_log.txt

# Cache
*.cache
.cache/

# Temporary files
temp_unnecessary_files/
*.tmp
*.temp
*.bak

# Test outputs
*_output.json
*_result.json
*_response.json
lambda_*.json

# Excel test files
*.xlsx
!test_events/*.xlsx

# MacOS
.DS_Store

# Windows
Thumbs.db
ehthumbs.db

# AWS
.aws/
"""
    
    gitignore_path = PROJECT_ROOT / ".gitignore"
    with open(gitignore_path, 'w') as f:
        f.write(gitignore_content)
    
    print(f"\nCreated/updated .gitignore")

if __name__ == "__main__":
    print("Starting project cleanup...")
    moved, deleted, kept = clean_project()
    
    print("\n=== Files to be kept ===")
    # Group by directory
    from collections import defaultdict
    by_dir = defaultdict(list)
    
    for file in sorted(kept):
        dir_name = str(file.parent) if file.parent != Path('.') else 'root'
        by_dir[dir_name].append(file.name)
    
    for dir_name, files in sorted(by_dir.items()):
        print(f"\n{dir_name}/")
        for file in sorted(files):
            print(f"  - {file}") 