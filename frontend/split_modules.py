#!/usr/bin/env python3
"""
Module Extraction Script
Splits 99-all-javascript.js into focused modules
"""
import re
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent
JS_DIR = FRONTEND_DIR / 'src' / 'js'
SOURCE_FILE = JS_DIR / '99-all-javascript.js'

# Define module extraction rules
# Each tuple: (output_file, start_pattern, end_pattern, description, dependencies)
MODULES = [
    (
        '05-chat.js',
        r'function showMessage\(',
        r'function createEmailCard\(',
        'Message display and markdown rendering',
        '00-config.js (globalState)'
    ),
    (
        '06-upload.js',
        r'function formatFileSize\(',
        r'async function fetchClarifyingQuestions',
        'File upload, drag-drop, S3 operations',
        '00-config.js (globalState, API_BASE), 04-cards.js (createCard, showThinkingInCard)'
    ),
    (
        '07-email-validation.js',
        r'function validateEmail\(',
        r'function formatFileSize\(',
        'Email validation and verification flow',
        '00-config.js (globalState, API_BASE), 04-cards.js (createCard)'
    ),
    (
        '14-account.js',
        r'function addCreditsToCart\(',
        r'function createThinkingIndicator\(',
        'Account balance, credits, and payment integration',
        '00-config.js (globalState, API_BASE, ENV_CONFIG)'
    ),
]

def extract_function_block(lines, start_idx):
    """Extract a complete function or code block starting at start_idx"""
    # Find the opening brace
    brace_count = 0
    in_function = False
    function_lines = []

    for i in range(start_idx, len(lines)):
        line = lines[i]
        function_lines.append(line)

        # Count braces
        for char in line:
            if char == '{':
                brace_count += 1
                in_function = True
            elif char == '}':
                brace_count -= 1
                if in_function and brace_count == 0:
                    return function_lines, i + 1

    return function_lines, len(lines)

def find_pattern_line(lines, pattern, start=0):
    """Find the line number where pattern matches"""
    regex = re.compile(pattern)
    for i in range(start, len(lines)):
        if regex.search(lines[i]):
            # Back up to include any comments above the function
            j = i - 1
            while j >= start and (lines[j].strip().startswith('//') or lines[j].strip() == ''):
                j -= 1
            return j + 1
    return -1

def extract_module(lines, start_pattern, end_pattern):
    """Extract lines between start and end patterns"""
    start_line = find_pattern_line(lines, start_pattern)
    end_line = find_pattern_line(lines, end_pattern, start_line + 1) if end_pattern else len(lines)

    if start_line == -1:
        print(f'  [WARN] Start pattern not found: {start_pattern}')
        return []

    if end_pattern and end_line == -1:
        print(f'  [WARN] End pattern not found: {end_pattern}, extracting to end')
        end_line = len(lines)

    return lines[start_line:end_line]

def create_module_header(filename, description, dependencies):
    """Create a module header comment"""
    return f'''/* ========================================
 * {filename.replace('.js', '').replace('-', ' ').title()}
 * {description}
 *
 * Dependencies: {dependencies}
 * ======================================== */

'''

def main():
    print('[SPLIT] Starting module extraction...')

    # Read source file
    if not SOURCE_FILE.exists():
        print(f'[ERROR] Source file not found: {SOURCE_FILE}')
        return

    content = SOURCE_FILE.read_text(encoding='utf-8')
    lines = content.splitlines(keepends=True)

    print(f'[SPLIT] Loaded {len(lines)} lines from {SOURCE_FILE.name}')

    # Extract each module
    for module_file, start_pat, end_pat, desc, deps in MODULES:
        print(f'[SPLIT] Extracting {module_file}...')

        module_lines = extract_module(lines, start_pat, end_pat)

        if not module_lines:
            print(f'  [SKIP] No content found for {module_file}')
            continue

        # Create module with header
        header = create_module_header(module_file, desc, deps)
        module_content = header + ''.join(module_lines)

        # Write module file
        output_path = JS_DIR / module_file
        output_path.write_text(module_content, encoding='utf-8')

        line_count = len(module_lines)
        byte_size = len(module_content.encode('utf-8'))
        print(f'  [SUCCESS] Created {module_file} ({line_count} lines, {byte_size:,} bytes)')

    print('[SPLIT] Module extraction complete!')

if __name__ == '__main__':
    main()
