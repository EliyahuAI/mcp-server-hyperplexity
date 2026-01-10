#!/usr/bin/env python3
"""
Hyperplexity Frontend Build Script

Assembles modular frontend source files into a single HTML file
for Squarespace deployment.

Usage:
    python frontend/build.py
    python frontend/build.py --watch    # Rebuild on changes
    python frontend/build.py --minify   # Minify output (future)
"""
import os
import sys
import time
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent
SRC_DIR = FRONTEND_DIR / 'src'
OUTPUT_FILE = FRONTEND_DIR / 'Hyperplexity_frontend.html'

def load_sorted_files(directory: Path, extension: str) -> str:
    """Load and concatenate files sorted by numeric prefix."""
    files = sorted(directory.glob(f'*{extension}'))
    contents = []

    for f in files:
        # Add file marker for debugging
        contents.append(f'\n/* ========== {f.name} ========== */\n')
        contents.append(f.read_text(encoding='utf-8'))

    return '\n'.join(contents)

def build():
    """Assemble the frontend from source modules."""
    print(f'[BUILD] Starting frontend build...')
    start_time = time.time()

    # Verify source directory exists
    if not SRC_DIR.exists():
        print(f'[ERROR] Source directory not found: {SRC_DIR}')
        print(f'[ERROR] Run migration first to create source structure.')
        sys.exit(1)

    # Load template
    template_file = SRC_DIR / 'template.html'
    if not template_file.exists():
        print(f'[ERROR] Template file not found: {template_file}')
        sys.exit(1)

    template = template_file.read_text(encoding='utf-8')

    # Concatenate CSS files
    styles_dir = SRC_DIR / 'styles'
    if styles_dir.exists():
        css_content = load_sorted_files(styles_dir, '.css')
        print(f'[BUILD] Loaded {len(list(styles_dir.glob("*.css")))} CSS files')
    else:
        css_content = '/* No styles directory found */'
        print(f'[WARN] No styles directory found')

    # Concatenate JS files
    js_dir = SRC_DIR / 'js'
    if js_dir.exists():
        js_content = load_sorted_files(js_dir, '.js')
        print(f'[BUILD] Loaded {len(list(js_dir.glob("*.js")))} JS files')
    else:
        js_content = '/* No js directory found */'
        print(f'[WARN] No js directory found')

    # Wrap JS in IIFE to match original structure
    js_wrapped = f'(function() {{\n{js_content}\n}})();'

    # Assemble output
    output = template.replace('{{CSS}}', css_content).replace('{{JS}}', js_wrapped)

    # Write output file
    OUTPUT_FILE.write_text(output, encoding='utf-8')

    elapsed = time.time() - start_time
    line_count = output.count('\n')
    byte_size = len(output.encode('utf-8'))

    print(f'[SUCCESS] Built {OUTPUT_FILE.name}')
    print(f'[SUCCESS] {line_count:,} lines, {byte_size:,} bytes in {elapsed:.2f}s')

def watch():
    """Watch for changes and rebuild automatically."""
    print(f'[WATCH] Watching for changes in {SRC_DIR}...')
    print(f'[WATCH] Press Ctrl+C to stop')

    last_mtime = 0

    while True:
        try:
            # Get latest modification time across all source files
            current_mtime = 0
            for f in SRC_DIR.rglob('*'):
                if f.is_file():
                    current_mtime = max(current_mtime, f.stat().st_mtime)

            if current_mtime > last_mtime:
                if last_mtime > 0:  # Skip first build message
                    print(f'\n[WATCH] Change detected, rebuilding...')
                build()
                last_mtime = current_mtime

            time.sleep(1)

        except KeyboardInterrupt:
            print(f'\n[WATCH] Stopped')
            break

def main():
    if '--watch' in sys.argv:
        watch()
    else:
        build()

if __name__ == '__main__':
    main()
