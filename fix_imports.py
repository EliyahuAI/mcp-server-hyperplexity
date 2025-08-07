#!/usr/bin/env python
"""
Fix all import statements in the interface lambda files.
Changes 'from src.lambdas.interface.' to 'from interface_lambda.'
and 'from src.shared.' to direct imports (since shared files are in package root).
"""
import re
from pathlib import Path

def fix_imports_in_file(file_path):
    """Fix imports in a single file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Fix interface imports
    content = re.sub(
        r'from src\.lambdas\.interface\.', 
        'from interface_lambda.', 
        content
    )
    
    # Fix shared imports - these are in the package root
    content = re.sub(
        r'from src\.shared\.(\w+) import',
        r'from \1 import',
        content
    )
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed imports in {file_path}")
        return True
    return False

def main():
    """Fix all imports in the interface lambda directory."""
    interface_dir = Path('src/lambdas/interface')
    
    if not interface_dir.exists():
        print(f"Directory {interface_dir} does not exist!")
        return
    
    fixed_count = 0
    for py_file in interface_dir.rglob('*.py'):
        if fix_imports_in_file(py_file):
            fixed_count += 1
    
    print(f"\nFixed imports in {fixed_count} files.")

if __name__ == '__main__':
    main() 