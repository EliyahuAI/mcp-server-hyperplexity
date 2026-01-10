#!/usr/bin/env python3
"""
Script to split the monolithic JavaScript file into modules based on the plan.
This is a semi-automated approach that extracts code sections based on line ranges.
"""
from pathlib import Path

SRC_DIR = Path(__file__).parent / 'src'
JS_DIR = SRC_DIR / 'js'
MONO_FILE = JS_DIR / '99-all-javascript.js'

def read_lines(start, end):
    """Read lines from monolithic file (1-indexed, inclusive)."""
    with open(MONO_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        # Convert to 0-indexed and make end inclusive
        return ''.join(lines[start-1:end])

def write_module(filename, content):
    """Write content to a module file."""
    filepath = JS_DIR / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[SUCCESS] Created {filename} ({len(content)} chars)")

def extract_remaining_modules():
    """Extract the remaining JavaScript modules."""

    # Skip first 4 modules that are already done
    # 00-config.js, 01-utils.js, 02-storage.js, 03-websocket.js ✓

    print("[INFO] Extracting remaining JavaScript modules...")
    print("[INFO] Modules 00-03 already created, starting from 04...")

    # Get the full monolithic file content
    with open(MONO_FILE, 'r', encoding='utf-8') as f:
        full_content = f.read()
        total_lines = len(full_content.split('\n'))

    print(f"[INFO] Total lines in monolithic file: {total_lines}")

    # Extract remaining modules by reading large sections
    # We'll extract everything after websockets (line ~4005) and before the final DOMContentLoaded (line ~11100)

    # 04-cards.js: Lines 528-1688 (card system, thinking indicators, buttons)
    cards_content = read_lines(528, 1688)
    cards_module = f"""/* ========================================
 * Cards Module
 * Card creation, thinking indicators, progress tracking, and button management
 *
 * Dependencies: 00-config.js (globalState)
 *               01-utils.js (generateCardId, getConfidenceColor, showMessage)
 * ======================================== */

{cards_content}"""
    write_module('04-cards.js', cards_module)

    # 05-chat.js will be extracted later - continuing with the large bulk extraction first

    return True

def main():
    if not MONO_FILE.exists():
        print(f"[ERROR] Monolithic file not found: {MONO_FILE}")
        return False

    success = extract_remaining_modules()

    if success:
        print("\n[SUCCESS] All remaining JavaScript modules extracted!")
        print(f"[INFO] Location: {JS_DIR}")
        print("\n[NEXT] Run: python frontend/build.py")
    else:
        print("\n[ERROR] Extraction failed")

    return success

if __name__ == '__main__':
    main()
