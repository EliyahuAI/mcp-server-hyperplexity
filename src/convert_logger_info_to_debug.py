#!/usr/bin/env python3
"""
Logger Info to Debug Converter

This script finds all logger.info lines that START with opening brackets
and converts them to logger.debug to reduce log verbosity.

Brackets detected at start of logger content: [ { (
Example: logger.info("[DEBUG] Processing data") -> logger.debug("[DEBUG] Processing data")
"""

import os
import re
import glob
from typing import List, Tuple

def starts_with_bracket(content: str) -> bool:
    """Check if content starts with any opening bracket: [ { ("""
    content = content.strip()
    if not content:
        return False
    # Remove quotes if present and check first character
    if content.startswith('"') or content.startswith("'"):
        # Handle quoted strings - look at first char after quote
        quote_char = content[0]
        if len(content) > 1:
            inner_content = content[1:]
            return inner_content.startswith('[') or inner_content.startswith('{') or inner_content.startswith('(')
    elif content.startswith('f"') or content.startswith("f'"):
        # Handle f-strings - look at first char after f"
        if len(content) > 2:
            inner_content = content[2:]
            return inner_content.startswith('[') or inner_content.startswith('{') or inner_content.startswith('(')

    return content.startswith('[') or content.startswith('{') or content.startswith('(')

def convert_file(file_path: str) -> Tuple[int, List[str]]:
    """
    Convert logger.info lines with brackets to logger.debug in a file.

    Returns:
        Tuple of (number_of_changes, list_of_changed_lines)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0, []

    changes = []
    modified_lines = []

    for i, line in enumerate(lines):
        # Look for logger.info patterns
        logger_info_match = re.search(r'(\s*)(.*?logger\.info\s*\()', line)

        if logger_info_match:
            # Extract just the logger.info call content (everything after the opening parenthesis)
            logger_call_start = line.find('logger.info(') + len('logger.info(')
            call_content = line[logger_call_start:]

            # Check if the logger call content starts with brackets
            if starts_with_bracket(call_content):
                # Replace logger.info with logger.debug
                new_line = line.replace('logger.info(', 'logger.debug(')
                lines[i] = new_line

                changes.append(f"Line {i+1}: {line.strip()} -> {new_line.strip()}")
                modified_lines.append(i+1)

    if changes:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print(f"[SUCCESS] Modified {file_path}: {len(changes)} changes")
        except Exception as e:
            print(f"[ERROR] Error writing {file_path}: {e}")
            return 0, []

    return len(changes), modified_lines

def find_python_files(root_dir: str) -> List[str]:
    """Find all Python files in the directory tree."""
    python_files = []

    # Walk through all directories
    for root, dirs, files in os.walk(root_dir):
        # Skip common non-source directories
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.pytest_cache', 'node_modules']]

        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))

    return python_files

def clean_logger_file(file_path: str) -> int:
    """
    Clean a single file by converting logger.info with brackets to logger.debug.

    Args:
        file_path: Path to the Python file to clean

    Returns:
        Number of changes made
    """
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return 0

    changes, _ = convert_file(file_path)
    if changes > 0:
        print(f"[SUCCESS] Cleaned {file_path}: {changes} conversions")
    return changes

def clean_entire_codebase(root_dir: str = None) -> int:
    """
    Clean all Python files in the codebase.

    Args:
        root_dir: Root directory to scan (defaults to script directory)

    Returns:
        Total number of changes made
    """
    if root_dir is None:
        root_dir = os.path.dirname(os.path.abspath(__file__))

    python_files = find_python_files(root_dir)
    total_changes = 0

    print(f"[SCAN] Found {len(python_files)} Python files to process")

    for file_path in python_files:
        changes, _ = convert_file(file_path)
        if changes > 0:
            total_changes += changes
            rel_path = os.path.relpath(file_path, root_dir)
            print(f"  [MODIFIED] {rel_path}: {changes} conversions")

    return total_changes

def main():
    """Main function to convert logger.info to logger.debug in interface lambda handlers."""
    print("[INFO] Logger Info to Debug Converter")
    print("Converting logger.info lines that start with brackets to logger.debug...")

    # Get the script directory (should be in project root)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Target the interface lambda handlers directory
    interface_handlers_dir = os.path.join(script_dir, "src", "lambdas", "interface", "handlers")

    if not os.path.exists(interface_handlers_dir):
        print(f"[ERROR] Interface handlers directory not found: {interface_handlers_dir}")
        return

    # Find all Python files in handlers directory
    python_files = []
    for root, dirs, files in os.walk(interface_handlers_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))

    if not python_files:
        print(f"[ERROR] No Python files found in {interface_handlers_dir}")
        return

    print(f"\n[SCAN] Processing {len(python_files)} interface handler files")

    total_changes = 0
    modified_files = 0

    for file_path in python_files:
        changes = clean_logger_file(file_path)
        if changes > 0:
            modified_files += 1
            total_changes += changes

    print(f"\n[SUMMARY]")
    print(f"  Files processed: {len(python_files)}")
    print(f"  Files modified: {modified_files}")
    print(f"  Total conversions: {total_changes}")

    if total_changes > 0:
        print(f"\n[SUCCESS] Conversion complete! {total_changes} logger.info lines with brackets converted to logger.debug")
        print(f"[INFO] This will reduce log verbosity while preserving debug information")
    else:
        print(f"\n[SUCCESS] No logger.info lines with brackets found - logging is already clean!")

if __name__ == "__main__":
    main()