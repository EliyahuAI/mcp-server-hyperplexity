# Hyperplexity Frontend Refactoring Plan

## Current State

The frontend is a single monolithic HTML file (`frontend/perplexity_validator_interface2.html`) containing:
- ~14,000+ lines of code
- Inline CSS styles
- Inline JavaScript
- Likely vestigial/dead code accumulated over time

This file is copy-pasted into Squarespace for deployment, which is why it must remain a single file for production.

## Problems

1. **Unwieldy**: Too large to review or navigate effectively
2. **Vestigial code**: Functions that are no longer called
3. **Difficult maintenance**: Hard to find where features are implemented
4. **Poor git diffs**: Changes anywhere affect the single massive file
5. **No modularity**: Everything in global scope, dependencies unclear

## Recommended Architecture

### Directory Structure

```
frontend/
├── build.py                        # Assembly script
├── Hyperplexity_frontend.html      # Generated output (for Squarespace)
├── .gitignore                      # Ignore generated file
├── src/
│   ├── template.html               # Base HTML with placeholders
│   ├── styles/
│   │   ├── 00-variables.css        # CSS variables, colors, fonts
│   │   ├── 01-base.css             # Reset, body, typography
│   │   ├── 02-layout.css           # Main layout, containers
│   │   ├── 03-cards.css            # Card system styles
│   │   ├── 04-chat.css             # Chat/conversation UI
│   │   ├── 05-forms.css            # Inputs, buttons, dropzones
│   │   ├── 06-modals.css           # Modal dialogs
│   │   ├── 07-tables.css           # Data tables, results
│   │   └── 08-animations.css       # Transitions, keyframes
│   └── js/
│       ├── 00-config.js            # Constants, API endpoints, globalState
│       ├── 01-utils.js             # Helper functions (generateCardId, formatters, etc)
│       ├── 02-storage.js           # localStorage, session management
│       ├── 03-websocket.js         # WebSocket connection, message routing
│       ├── 04-cards.js             # Card creation, registerCardHandler, lifecycle
│       ├── 05-chat.js              # addChatMessage, streaming text, chat UI
│       ├── 06-upload.js            # File upload, drag-drop, presigned URLs
│       ├── 07-email-validation.js  # Email validation flow
│       ├── 08-config-generation.js # Config generation UI and handlers
│       ├── 09-table-maker.js       # Table maker conversation flow
│       ├── 10-upload-interview.js  # Upload interview flow
│       ├── 11-preview.js           # Preview validation flow
│       ├── 12-validation.js        # Full validation flow
│       ├── 13-results.js           # Results display, downloads
│       ├── 14-account.js           # Account balance, credits
│       └── 99-init.js              # DOMContentLoaded, event bindings, startup
```

### Template File (src/template.html)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hyperplexity - AI-Powered Data Validation</title>
    <style>
{{CSS}}
    </style>
</head>
<body>
    <div id="app">
        <div id="cards-container"></div>
    </div>

    <script>
{{JS}}
    </script>
</body>
</html>
```

### Build Script (build.py)

```python
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

    # Assemble output
    output = template.replace('{{CSS}}', css_content).replace('{{JS}}', js_content)

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
```

## Module Responsibilities

### JavaScript Modules

| Module | Responsibility | Key Functions |
|--------|---------------|---------------|
| `00-config.js` | Configuration and state | `API_BASE`, `WS_URL`, `globalState`, feature flags |
| `01-utils.js` | Utility functions | `generateCardId()`, `formatCurrency()`, `debounce()`, `escapeHtml()` |
| `02-storage.js` | Persistence | `saveToLocalStorage()`, `loadFromLocalStorage()`, session handling |
| `03-websocket.js` | WebSocket management | `connectWebSocket()`, `sendWebSocketMessage()`, message routing |
| `04-cards.js` | Card system | `createCard()`, `registerCardHandler()`, `showFinalCardState()`, `showThinkingInCard()` |
| `05-chat.js` | Chat UI | `addChatMessage()`, `streamText()`, typing indicators |
| `06-upload.js` | File uploads | `handleFileUpload()`, drag-drop handlers, presigned URL flow |
| `07-email-validation.js` | Email flow | `requestEmailValidation()`, `validateEmailCode()`, email UI |
| `08-config-generation.js` | Config generation | `handleConfigWebSocketMessage()`, config UI, refinement flow |
| `09-table-maker.js` | Table maker | `startTableConversation()`, `handleTableMakerUpdate()`, column definitions |
| `10-upload-interview.js` | Upload interview | `createUploadInterviewCard()`, `sendInterviewMessage()`, `handleUploadInterviewUpdate()` |
| `11-preview.js` | Preview flow | `triggerPreviewValidation()`, preview results display |
| `12-validation.js` | Full validation | `startFullValidation()`, progress tracking, batch handling |
| `13-results.js` | Results display | Results tables, download buttons, export functions |
| `14-account.js` | Account management | `getAccountBalance()`, credits display, payment integration |
| `99-init.js` | Initialization | `DOMContentLoaded` handler, initial card creation, event binding |

### CSS Modules

| Module | Responsibility |
|--------|---------------|
| `00-variables.css` | CSS custom properties (colors, spacing, fonts) |
| `01-base.css` | Reset, body styles, typography |
| `02-layout.css` | Main container, grid, flexbox utilities |
| `03-cards.css` | Card component styles |
| `04-chat.css` | Chat bubbles, conversation UI |
| `05-forms.css` | Inputs, buttons, dropzones, file upload |
| `06-modals.css` | Modal dialogs, overlays |
| `07-tables.css` | Data tables, results grids |
| `08-animations.css` | Keyframes, transitions, loading states |

## Migration Strategy

### Phase 1: Setup (Do First)

1. Create directory structure:
   ```
   frontend/src/
   frontend/src/styles/
   frontend/src/js/
   ```

2. Create `build.py` script (copy from above)

3. Create `template.html` with basic structure

4. Add to `.gitignore`:
   ```
   frontend/Hyperplexity_frontend.html
   ```

### Phase 2: Extract CSS

1. Create `00-variables.css` - extract all CSS custom properties
2. Work through remaining CSS modules
3. Test build produces working output
4. Compare visual output with original

### Phase 3: Extract JavaScript (Order Matters!)

Extract in this order to respect dependencies:

1. **00-config.js** - Extract `globalState`, constants, API URLs
2. **01-utils.js** - Extract pure utility functions
3. **02-storage.js** - Extract localStorage functions
4. **03-websocket.js** - Extract WebSocket code
5. **04-cards.js** - Extract card system (depends on utils)
6. **05-chat.js** - Extract chat functions (depends on cards)
7. **06-upload.js** - Extract upload handling
8. Continue with feature modules...
9. **99-init.js** - Extract initialization (depends on everything)

### Phase 4: Cleanup

1. Search for unused functions in each module
2. Remove vestigial code
3. Add JSDoc comments to key functions
4. Document module dependencies at top of each file

## Testing Strategy

After each extraction:

1. Run `python frontend/build.py`
2. Open `Hyperplexity_frontend.html` in browser
3. Test the specific feature that was extracted
4. Check browser console for errors
5. Verify WebSocket connection works
6. Test full flow: upload -> interview -> config -> preview

## Finding Vestigial Code

Once modularized, find dead code by:

1. **Search for function definitions** in each module
2. **Grep for function calls** across all modules
3. Functions with 0 external calls (except exports) are candidates for removal
4. Use browser DevTools Coverage tab to identify unused code at runtime

## Example: Extracting a Module

Here's how to extract `05-chat.js`:

1. Find all chat-related functions in the monolith:
   - `addChatMessage()`
   - `streamText()` (if exists)
   - `createChatBubble()` (if exists)
   - Chat-related event handlers

2. Create `frontend/src/js/05-chat.js`:
   ```javascript
   /* ========================================
    * Chat UI Module
    * Handles chat message display and streaming
    *
    * Dependencies: 04-cards.js (card containers)
    * ======================================== */

   async function addChatMessage(cardId, role, message) {
       // ... extracted code
   }

   // ... other chat functions
   ```

3. Remove the code from the original file

4. Build and test

## Deployment Workflow

After refactoring is complete:

1. Make changes to source modules in `frontend/src/`
2. Run `python frontend/build.py`
3. Copy contents of `Hyperplexity_frontend.html` to Squarespace
4. Test in production

Optional: Set up `--watch` mode during development:
```bash
python frontend/build.py --watch
```

## Notes

- Keep the original `perplexity_validator_interface2.html` until migration is complete
- The numeric prefixes (00-, 01-, etc.) ensure correct concatenation order
- Each JS module should document its dependencies at the top
- CSS order matters less but keep variables first
- Consider adding source maps in future for debugging
