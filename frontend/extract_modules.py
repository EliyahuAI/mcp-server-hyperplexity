#!/usr/bin/env python3
"""
Frontend Module Extraction Script
Automatically extracts CSS and JavaScript modules from the monolithic HTML file.
"""

import os
from pathlib import Path

# Paths
FRONTEND_DIR = Path(__file__).parent
HTML_FILE = FRONTEND_DIR / 'perplexity_validator_interface2.html'
SRC_DIR = FRONTEND_DIR / 'src'
STYLES_DIR = SRC_DIR / 'styles'
JS_DIR = SRC_DIR / 'js'

def read_lines(file_path, start_line, end_line):
    """Read specific lines from a file (1-indexed)."""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        # Convert to 0-indexed and extract
        return ''.join(lines[start_line-1:end_line])

def write_module(file_path, content, header):
    """Write a module file with header."""
    full_content = f"{header}\n\n{content}"
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    print(f"[SUCCESS] Created {file_path.name}")

# CSS Extraction Map (already created: 00, 01, 02, 03, 04)
css_modules = {
    '05-forms.css': {
        'header': """/* ========================================
 * Forms Module
 * Input fields, buttons, dropzones, file upload, and privacy checkbox
 *
 * Dependencies: 00-variables.css
 * ======================================== */""",
        'lines': (759, 867)  # Forms section
    },
    '06-modals.css': {
        'header': """/* ========================================
 * Modals Module
 * Modal dialogs, overlays, and table maker modal
 *
 * Dependencies: 00-variables.css
 * ======================================== */""",
        'lines': (1586, 1967)  # Table maker modal styles
    },
    '07-tables.css': {
        'header': """/* ========================================
 * Tables Module
 * Data tables, results grids, and table preview
 *
 * Dependencies: 00-variables.css
 * ======================================== */""",
        'lines': (1738, 1783)  # Table preview section
    },
    '08-animations.css': {
        'header': """/* ========================================
 * Animations Module
 * Keyframes, transitions, and animation utilities
 *
 * Dependencies: None
 * ======================================== */""",
        'lines': (256, 1250)  # All animation keyframes
    }
}

# Extract remaining CSS modules
print("[INFO] Extracting remaining CSS modules...")
for filename, config in css_modules.items():
    file_path = STYLES_DIR / filename
    if not file_path.exists():
        start, end = config['lines']
        content = read_lines(HTML_FILE, start, end)
        write_module(file_path, content, config['header'])

print("\n[SUCCESS] All CSS modules extracted!")
print(f"[INFO] CSS modules location: {STYLES_DIR}")
