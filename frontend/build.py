#!/usr/bin/env python3
"""
Hyperplexity Frontend Build Script

Assembles modular frontend source files into a single HTML file
for Squarespace deployment.

Usage:
    python frontend/build.py
    python frontend/build.py --watch              # Rebuild on changes
    python frontend/build.py --minify             # Minify output (future)
    python frontend/build.py --standalone metadata.json --output results.html
    python frontend/build.py --standalone-template --output viewer.html
"""
import os
import sys
import time
import json
import argparse
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent
SRC_DIR = FRONTEND_DIR / 'src'
OUTPUT_FILE = FRONTEND_DIR / 'Hyperplexity_FullScript_Temp-dev.html'
STANDALONE_TEMPLATE = SRC_DIR / 'standalone-table-template.html'

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

    # Also write a copy without -dev suffix for production use
    PROD_OUTPUT_FILE = FRONTEND_DIR / 'Hyperplexity_FullScript_Temp.html'
    PROD_OUTPUT_FILE.write_text(output, encoding='utf-8')

    # Write account page copies (same content, deployed at /account path)
    ACCOUNT_DEV_FILE = FRONTEND_DIR / 'account-dev.html'
    ACCOUNT_FILE = FRONTEND_DIR / 'account.html'
    ACCOUNT_DEV_FILE.write_text(output, encoding='utf-8')
    ACCOUNT_FILE.write_text(output, encoding='utf-8')

    elapsed = time.time() - start_time
    line_count = output.count('\n')
    byte_size = len(output.encode('utf-8'))

    print(f'[SUCCESS] Built {OUTPUT_FILE.name}')
    print(f'[SUCCESS] Also copied to {PROD_OUTPUT_FILE.name}')
    print(f'[SUCCESS] Also copied to {ACCOUNT_DEV_FILE.name} and {ACCOUNT_FILE.name}')
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


def load_table_css() -> str:
    """Load table-specific CSS from 07-tables.css."""
    css_file = SRC_DIR / 'styles' / '07-tables.css'
    if not css_file.exists():
        print(f'[WARN] Table CSS file not found: {css_file}')
        return '/* Table CSS not found */'
    return css_file.read_text(encoding='utf-8')


def load_interactive_table_js() -> str:
    """Load InteractiveTable module from 16-interactive-table.js."""
    js_file = SRC_DIR / 'js' / '16-interactive-table.js'
    if not js_file.exists():
        print(f'[ERROR] InteractiveTable JS not found: {js_file}')
        sys.exit(1)
    return js_file.read_text(encoding='utf-8')


def build_standalone(
    metadata_file: Path = None,
    output_file: Path = None,
    title: str = 'Table Results',
    subtitle: str = ''
):
    """
    Generate standalone HTML viewer with optional embedded metadata.

    Args:
        metadata_file: Optional path to JSON metadata file to embed
        output_file: Output HTML file path
        title: Page title
        subtitle: Page subtitle
    """
    print(f'[STANDALONE] Building standalone table viewer...')
    start_time = time.time()

    # Check template exists
    if not STANDALONE_TEMPLATE.exists():
        print(f'[ERROR] Standalone template not found: {STANDALONE_TEMPLATE}')
        sys.exit(1)

    template = STANDALONE_TEMPLATE.read_text(encoding='utf-8')

    # Load table CSS
    table_css = load_table_css()
    print(f'[STANDALONE] Loaded table CSS ({len(table_css):,} chars)')

    # Load InteractiveTable JS
    table_js = load_interactive_table_js()
    print(f'[STANDALONE] Loaded InteractiveTable JS ({len(table_js):,} chars)')

    # Load metadata if provided
    if metadata_file:
        if not metadata_file.exists():
            print(f'[ERROR] Metadata file not found: {metadata_file}')
            sys.exit(1)
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        metadata_json = json.dumps(metadata, indent=None)
        print(f'[STANDALONE] Loaded metadata ({len(metadata.get("rows", [])):,} rows)')

        # Use metadata title if available and not overridden
        if not title or title == 'Table Results':
            title = metadata.get('title', title)
    else:
        # No metadata - use null so viewer will look for URL param
        metadata_json = 'null'

    # Build output
    output = template
    output = output.replace('{{TABLE_CSS}}', table_css)
    output = output.replace('{{TABLE_JS}}', table_js)
    output = output.replace('{{METADATA_JSON}}', metadata_json)
    output = output.replace('{{TITLE}}', title)
    output = output.replace('{{SUBTITLE}}', subtitle)

    # Write output
    if output_file is None:
        output_file = FRONTEND_DIR / 'standalone_table_viewer.html'

    output_file.write_text(output, encoding='utf-8')

    elapsed = time.time() - start_time
    line_count = output.count('\n')
    byte_size = len(output.encode('utf-8'))

    print(f'[SUCCESS] Built {output_file.name}')
    print(f'[SUCCESS] {line_count:,} lines, {byte_size:,} bytes in {elapsed:.2f}s')

    if metadata_file:
        print(f'[SUCCESS] Metadata embedded from: {metadata_file}')
    else:
        print(f'[INFO] No metadata embedded. Use ?metadata=URL to load from URL.')


def main():
    parser = argparse.ArgumentParser(
        description='Hyperplexity Frontend Build Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python frontend/build.py                          # Build main frontend
  python frontend/build.py --watch                  # Watch mode
  python frontend/build.py --standalone data.json   # Standalone with embedded data
  python frontend/build.py --standalone-template    # Standalone template (no data)
        """
    )

    parser.add_argument('--watch', action='store_true',
                        help='Watch for changes and rebuild automatically')
    parser.add_argument('--standalone', metavar='METADATA_JSON', nargs='?', const='',
                        help='Build standalone table viewer. Optionally embed metadata JSON.')
    parser.add_argument('--standalone-template', action='store_true',
                        help='Build standalone template (no embedded data)')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Output file path for standalone builds')
    parser.add_argument('--title', default='Table Results',
                        help='Title for standalone viewer')
    parser.add_argument('--subtitle', default='',
                        help='Subtitle for standalone viewer')

    args = parser.parse_args()

    # Handle standalone builds
    if args.standalone is not None or args.standalone_template:
        metadata_file = None
        if args.standalone and args.standalone != '':
            metadata_file = Path(args.standalone)

        output_file = Path(args.output) if args.output else None

        build_standalone(
            metadata_file=metadata_file,
            output_file=output_file,
            title=args.title,
            subtitle=args.subtitle
        )
    elif args.watch:
        watch()
    else:
        build()


if __name__ == '__main__':
    main()
