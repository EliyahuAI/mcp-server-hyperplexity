#!/usr/bin/env python3
"""
JavaScript Extraction Script
Extracts JavaScript from monolithic HTML into modular files.
"""

import re
from pathlib import Path

# Paths
FRONTEND_DIR = Path(__file__).parent
HTML_FILE = FRONTEND_DIR / 'perplexity_validator_interface2.html'
JS_DIR = FRONTEND_DIR / 'src' / 'js'

def read_file(file_path):
    """Read entire file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def write_module(file_path, content, header):
    """Write a module file with header."""
    full_content = f"{header}\n\n{content}"
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    print(f"[SUCCESS] Created {file_path.name}")

# Read full HTML
html_content = read_file(HTML_FILE)

# Extract JavaScript content (between <script> and </script>)
script_match = re.search(r'<script>\s*\n(.*?)\n\s*</script>', html_content, re.DOTALL)
if not script_match:
    print("[ERROR] Could not find JavaScript section")
    exit(1)

js_content = script_match.group(1)
print(f"[INFO] Found JavaScript section: {len(js_content)} characters")

# Split into lines for analysis
js_lines = js_content.split('\n')
print(f"[INFO] Total JavaScript lines: {len(js_lines)}")

# Define module extraction configuration
# Format: (filename, start_pattern, end_pattern_or_lines, header)
js_modules = [
    {
        'filename': '00-config.js',
        'header': '''/* ========================================
 * Configuration Module
 * Environment configuration, global state, and constants
 *
 * Dependencies: None
 * ======================================== */''',
        'content_func': lambda lines: extract_config_module(lines)
    },
    {
        'filename': '01-utils.js',
        'header': '''/* ========================================
 * Utility Functions Module
 * Helper functions, formatters, and validators
 *
 * Dependencies: None
 * ======================================== */''',
        'content_func': lambda lines: extract_utils_module(lines)
    },
    {
        'filename': '02-storage.js',
        'header': '''/* ========================================
 * Storage Module
 * LocalStorage and session management
 *
 * Dependencies: None
 * ======================================== */''',
        'content_func': lambda lines: extract_storage_module(lines)
    },
    {
        'filename': '03-websocket.js',
        'header': '''/* ========================================
 * WebSocket Module
 * WebSocket connection management and message routing
 *
 * Dependencies: 00-config.js, 02-storage.js
 * ======================================== */''',
        'content_func': lambda lines: extract_websocket_module(lines)
    },
    {
        'filename': '04-cards.js',
        'header': '''/* ========================================
 * Cards Module
 * Card creation, lifecycle management, and handlers
 *
 * Dependencies: 00-config.js, 01-utils.js
 * ======================================== */''',
        'content_func': lambda lines: extract_cards_module(lines)
    },
    {
        'filename': '05-chat.js',
        'header': '''/* ========================================
 * Chat Module
 * Chat messages, thinking indicators, and progress display
 *
 * Dependencies: 00-config.js, 01-utils.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_chat_module(lines)
    },
    {
        'filename': '06-upload.js',
        'header': '''/* ========================================
 * Upload Module
 * File upload handling, drag-drop, and validation
 *
 * Dependencies: 00-config.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_upload_module(lines)
    },
    {
        'filename': '07-email-validation.js',
        'header': '''/* ========================================
 * Email Validation Module
 * Email validation flow and UI
 *
 * Dependencies: 00-config.js, 01-utils.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_email_module(lines)
    },
    {
        'filename': '08-config-generation.js',
        'header': '''/* ========================================
 * Config Generation Module
 * Configuration generation and refinement UI
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_config_gen_module(lines)
    },
    {
        'filename': '09-table-maker.js',
        'header': '''/* ========================================
 * Table Maker Module
 * Table maker conversation flow and UI
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */''',
        'content_func': lambda lines: extract_table_maker_module(lines)
    },
    {
        'filename': '10-upload-interview.js',
        'header': '''/* ========================================
 * Upload Interview Module
 * Upload interview conversation flow
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */''',
        'content_func': lambda lines: extract_upload_interview_module(lines)
    },
    {
        'filename': '11-preview.js',
        'header': '''/* ========================================
 * Preview Module
 * Preview validation flow and results display
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_preview_module(lines)
    },
    {
        'filename': '12-validation.js',
        'header': '''/* ========================================
 * Validation Module
 * Full validation flow and progress tracking
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */''',
        'content_func': lambda lines: extract_validation_module(lines)
    },
    {
        'filename': '13-results.js',
        'header': '''/* ========================================
 * Results Module
 * Results display, downloads, and exports
 *
 * Dependencies: 00-config.js, 01-utils.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_results_module(lines)
    },
    {
        'filename': '14-account.js',
        'header': '''/* ========================================
 * Account Module
 * Account balance, credits, and payment integration
 *
 * Dependencies: 00-config.js, 01-utils.js, 04-cards.js
 * ======================================== */''',
        'content_func': lambda lines: extract_account_module(lines)
    },
    {
        'filename': '99-init.js',
        'header': '''/* ========================================
 * Initialization Module
 * DOMContentLoaded handler and app initialization
 *
 * Dependencies: All modules
 * ======================================== */''',
        'content_func': lambda lines: extract_init_module(lines)
    }
]

# Function extraction helpers
def find_function_block(lines, start_idx):
    """Find complete function block starting from start_idx."""
    indent_level = 0
    func_lines = []
    in_function = False

    for i in range(start_idx, len(lines)):
        line = lines[i]
        func_lines.append(line)

        # Count braces
        indent_level += line.count('{') - line.count('}')

        if '{' in line and not in_function:
            in_function = True

        # Function complete when we return to initial indent level
        if in_function and indent_level == 0:
            return func_lines, i

    return func_lines, len(lines)

def extract_functions_by_pattern(lines, patterns):
    """Extract functions matching given patterns."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        matched = False

        for pattern in patterns:
            if re.search(pattern, line):
                func_block, end_idx = find_function_block(lines, i)
                result.extend(func_block)
                result.append('')  # Add blank line after function
                i = end_idx
                matched = True
                break

        if not matched:
            i += 1

    return '\n'.join(result)

# Module extraction functions (these will extract specific functions)
def extract_config_module(lines):
    """Extract configuration and global state."""
    # Get lines from start until after globalState declaration
    result = []
    for i, line in enumerate(lines):
        result.append(line)
        if 'ensureProcessingState' in line and 'function' in line:
            # Get the complete function
            func_block, end_idx = find_function_block(lines, i)
            result = lines[:end_idx+1]
            break
    return '\n'.join(result)

def extract_utils_module(lines):
    """Extract utility functions."""
    patterns = [
        r'function validateEmail',
        r'function formatFileSize',
        r'function formatLocalDateTime',
        r'function generateCardId',
        r'function renderMarkdown',
        r'function isMobileDevice',
        r'function isPortraitMode',
        r'function truncateTickerText',
        r'function getConfidenceColor',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_storage_module(lines):
    """Extract localStorage functions."""
    patterns = [
        r'function getStoredEnvironment',
        r'function setEnvironment',
        r'function clearEnvironmentPreference',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_websocket_module(lines):
    """Extract WebSocket functions."""
    patterns = [
        r'function connectToSession',
        r'function routeMessage',
        r'function handleProcessingWebSocketMessage',
        r'function ensureWebSocketHealth',
        r'function isWebSocketHealthy',
        r'function setupWebSocketFallback',
        r'function registerCardHandler',
        r'function unregisterCardHandler',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_cards_module(lines):
    """Extract card-related functions."""
    patterns = [
        r'function createCard\(',
        r'function showFinalCardState',
        r'function createProgress',
        r'function createButtonRow',
        r'function markButtonSelected',
        r'function markButtonUnselected',
        r'function resetProcessButtons',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_chat_module(lines):
    """Extract chat and thinking indicator functions."""
    patterns = [
        r'function createThinkingIndicator',
        r'function showThinkingInCard',
        r'function updateThinkingInCard',
        r'function updateThinkingProgress',
        r'function completeThinkingInCard',
        r'function hideThinkingInCard',
        r'function startDynamicAnimations',
        r'function stopDynamicAnimations',
        r'function updateProgressTimestamp',
        r'function startDummyProgress',
        r'function stopDummyProgress',
        r'function markRealProgressUpdate',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_upload_module(lines):
    """Extract file upload functions."""
    patterns = [
        r'function createUploadCard',
        r'function setupFileUpload',
        r'function validateExcelFile',
        r'function validateConfigFile',
        r'function showUploadInfo',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_email_module(lines):
    """Extract email validation functions."""
    patterns = [
        r'function createEmailCard',
        r'function handleEmailValidated',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_config_gen_module(lines):
    """Extract config generation functions."""
    patterns = [
        r'function debounceConfigAction',
        r'function showColumnDefsPanel',  # if exists
        r'function handleConfigUpdate',  # if exists
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_table_maker_module(lines):
    """Extract table maker functions."""
    patterns = [
        r'function handleTableExecutionUpdate',
        r'function handleTableExecutionComplete',
        r'function handleTableExecutionRestructure',
        r'function handleTableExecutionUnrecoverable',
        r'function clearTableExecutionState',
        r'function showRequirementsBox',
        r'function showColumnsBoxes',
        r'function showDiscoveredRowsBox',
        r'function showClaimsInfoBox',
        r'function updateRowsBoxWithApproved',
        r'function collapseConversation',
        r'function restartTableMaker',
        r'function showInsufficientRowsMessage',
        r'function createRestructureDetails',
        r'function proceedWithTableMaker',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_upload_interview_module(lines):
    """Extract upload interview functions."""
    patterns = [
        r'function createUploadInterviewCard',  # if exists
        r'function proceedWithUpload',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_preview_module(lines):
    """Extract preview functions."""
    patterns = [
        r'function showPreviewResults',
        r'function autoTriggerPreview',
        r'function updatePreviewBalanceDisplay',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_validation_module(lines):
    """Extract validation functions."""
    patterns = [
        r'function handleValidationUpdate',  # if exists
        r'function handleValidationComplete',  # if exists
        r'function startFullValidation',  # if exists
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_results_module(lines):
    """Extract results display functions."""
    patterns = [
        r'function displayResults',  # if exists
        r'function downloadResults',  # if exists
        r'function createDownloadButton',  # if exists
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_account_module(lines):
    """Extract account/balance functions."""
    patterns = [
        r'function handleBalanceUpdate',
        r'function showBalanceNotification',
        r'function handleWarning',
        r'function showInsufficientBalanceError',
        r'function openAddCreditsPage',
        r'function setupBalanceRefreshOnReturn',
        r'function startOrderPolling',
        r'function stopOrderPolling',
        r'function updateAllBalanceDisplays',
        r'function addCreditsToCart',
        r'function addCreditsAndGoToCart',
        r'function needCredits',
        r'function checkProductComponent',
        r'function getCurrentUserEmail',
    ]
    return extract_functions_by_pattern(lines, patterns)

def extract_init_module(lines):
    """Extract initialization code (DOMContentLoaded)."""
    # Find DOMContentLoaded block
    result = []
    in_init = False
    indent_level = 0

    for line in lines:
        if 'DOMContentLoaded' in line:
            in_init = True

        if in_init:
            result.append(line)
            indent_level += line.count('{') - line.count('}')

            # End when we close the event listener
            if indent_level == 0 and len(result) > 1:
                break

    return '\n'.join(result)

# Extract all modules
print("\n[INFO] Extracting JavaScript modules...")
for module_config in js_modules:
    filename = module_config['filename']
    file_path = JS_DIR / filename

    if not file_path.exists():
        print(f"\n[INFO] Extracting {filename}...")
        content = module_config['content_func'](js_lines)

        if content.strip():
            write_module(file_path, content, module_config['header'])
        else:
            print(f"[WARN] No content extracted for {filename} - skipping")
    else:
        print(f"[SKIP] {filename} already exists")

print("\n[SUCCESS] JavaScript extraction complete!")
print(f"[INFO] Modules location: {JS_DIR}")
