# Interactive Results Viewer

The Interactive Results Viewer provides an interactive table interface for viewing validation results. Users can explore data with hover tooltips and click-through modals, and download results in Excel or JSON format.

## Overview

The viewer is integrated in four ways:

1. **Preview Card** - Shows interactive table with first 3 rows after preview completes
2. **Full Validation Card** - Shows interactive table with ALL rows after full validation completes
3. **Standalone Mode** - Access via URL with session parameters
4. **Demo Mode** - Public shared tables accessible via `?demo={name}` (no auth required)

## Integrated Viewer (Preview & Full Validation)

After preview or full validation completes, the interactive table is displayed directly in the results card.

### Preview Card Features
- Interactive table showing **first 3 rows** (preview data)
- Download buttons: **Download Excel**, **Download JSON (for AI)**, **Refine Configuration**
- Revert button (if applicable) on separate row

### Full Validation Card Features
- Interactive table showing **ALL rows** (complete validation data)
- Download buttons: **Download Excel**, **Download JSON (for AI)**, **Refine Configuration**
- Revert + Share Table + New Validation buttons on separate row

### Button Layout
```
┌─────────────────────────────────────────────────────────┐
│ [Download Excel] [Download JSON (for AI)] [Refine]       │
├─────────────────────────────────────────────────────────┤
│ [Revert to Previous] [Share Table] [New Validation]      │  (Full validation only)
└─────────────────────────────────────────────────────────┘
```

## Standalone Viewer Mode

### URL Parameters

```
https://eliyahu.ai/hyperplexity?mode=viewer&session=SESSION_ID&version=VERSION
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `mode` | Yes | Must be `viewer` to activate viewer mode |
| `session` | Yes* | Session ID (e.g., `session_20240124_abc123`) |
| `version` | No | Config version number (defaults to latest) |
| `path` | No* | Alternative: direct path to local JSON file for testing |

*Either `session` or `path` is required.

### Standalone Viewer Buttons

The standalone viewer shows: **Download Excel**, **Download JSON**, **Share Table**, **Update Table**.

### Examples

```
# View specific session results
?mode=viewer&session=session_20240124_185905_abc123

# View specific version
?mode=viewer&session=session_20240124_185905_abc123&version=2

# Local testing with JSON file
?mode=viewer&path=preview_table_metadata.json
```

## Demo Mode (Public Shared Tables)

Shared tables are publicly accessible without authentication via the `?demo=` URL parameter.

### URL Format

```
https://eliyahu.ai/hyperplexity?demo=table-slug-a1b2c3
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `demo` | Yes | Demo table slug (e.g., `q4-financial-results-a1b2c3`) |

### Demo Viewer Features
- No email or authentication required
- Interactive table with full hover/click functionality
- **Download Excel (for Humans)** - presigned S3 URL (if Excel was shared)
- **Download JSON (for AI)** - client-side blob download
- **Create Your Own Table** / **Validate New Text** - CTA button (requires email)

### Reference Check Detection

If the demo table's first two columns are "Claim ID" and "Claim Order", the CTA button changes from "Create Your Own Table" to "Validate New Text" and kicks users into Reference Check mode instead of the standard upload flow.

### How Sharing Works

1. User clicks **Share Table** on a fully validated session
2. A confirmation dialog warns about public access
3. Backend copies `table_metadata.json` and enhanced Excel to `demos/interactive_tables/{slug}/`
4. An `info.json` provenance file is created with source session, email hash, and timestamp
5. The share link (`?demo={slug}`) is copied to clipboard
6. Re-clicking Share on an already-shared table shows options to **Copy Link** or **Unshare**

### Demo Slug Format

Demo names are generated as `{slugified-table-name}-{6-char-md5-of-session-id}`:
```
"Q4 Financial Results" + session_20240124_abc123 → q4-financial-results-e7f2a1
```

The session hash suffix prevents collisions between tables with the same name.

## Authentication

The viewer (non-demo) requires email validation before displaying results. This ensures users can only access their own validation results.

Flow:
1. User navigates to viewer URL
2. If not validated, email validation card is shown
3. After validation, results are loaded and displayed
4. Session path is constructed using validated email: `results/{domain}/{email_prefix}/{session_id}/`

## Features

### Interactive Table

- **Hover Tooltips**: Quick preview of cell details on hover
- **Click Modals**: Full cell information with keyboard navigation (arrow keys, Escape)
- **Column Highlighting**: Visual emphasis on row identifiers
- **Confidence Colors**: Color-coded cells based on validation confidence (HIGH/MEDIUM/LOW)
- **General Notes**: Collapsible section with table-level notes and methodology

### Downloads

Two download options are available:

| Button | Format | Description |
|--------|--------|-------------|
| Download Excel (for Humans) | `.xlsx` | Full enhanced Excel with formatting, comments, and metadata |
| Download JSON (for AI) | `.json` | Raw table_metadata for programmatic use or AI analysis |

Both downloads use client-side blob creation (no page navigation).

### Share Table

The Share button appears after full validation completes and in the standalone viewer. It publishes the validation results as a public demo table.

**Share flow:**
1. Click Share Table
2. Backend checks if already shared via `checkShareStatus`
3. If not shared: confirmation dialog with public access warning → Share Publicly
4. If already shared: dialog shows existing link → Copy Link or Unshare
5. On share: link is copied to clipboard automatically

**Unshare** removes all demo files from S3 (table_metadata, Excel, info.json).

## Architecture

### Frontend Components

#### `12-validation.js` - Full Validation Integration

| Function | Description |
|----------|-------------|
| `fetchAndRenderValidationTable(cardId, sessionId)` | Fetches full validation data and renders interactive table |

Called after full validation completes. Requests data with `is_preview: false` to get all rows. The COMPLETED handler and `createCompletionCard()` both include a Share Table button.

#### `13-results.js` - Preview Integration

Shows interactive table using `InteractiveTable.render()` with preview data (3 rows) delivered via WebSocket. No Share button (preview data is not meaningful to share).

#### `18-viewer-mode.js` - Standalone Viewer & Demo Mode

| Function | Description |
|----------|-------------|
| `initViewerMode()` | Entry point when `mode=viewer` detected |
| `initDemoMode()` | Entry point when `?demo=` detected |
| `loadAndDisplayResults(params)` | Fetches data from API and renders |
| `loadAndDisplayDemo(tableName)` | Fetches demo data (no auth) and renders |
| `createResultsViewerCard(options)` | Creates viewer card (can be called from anywhere) |
| `displayResultsInCard(cardId, data)` | Renders table and download/share buttons |
| `displayDemoResultsInCard(cardId, data, tableName)` | Renders demo table with download/CTA buttons |
| `showFullValidationResults(data)` | Convenience function for post-validation display |
| `downloadJsonMetadata(metadata, button)` | Client-side JSON download (blob, no navigation) |
| `handleShareTable(cardId, button, data)` | Share/unshare flow with status check and dialog |
| `showShareConfirmationDialog(isShared, demoName)` | Modal with share/copy-link/unshare options |

#### Card Options

```javascript
createResultsViewerCard({
    cardId: 'optional-custom-id',      // Auto-generated if not provided
    title: 'Validation Results',        // Card header title
    subtitle: 'Session info',           // Card header subtitle
    infoHeaderText: 'Instructions...',  // Info banner text
    tableMetadata: { ... },             // Pre-loaded metadata (optional)
    downloadUrl: 'https://...'          // Pre-signed download URL (optional)
});
```

### Backend API

#### Action: `getViewerData`

**Endpoint:** `POST /validate`

**Request:**
```json
{
    "action": "getViewerData",
    "session_id": "session_20240124_abc123",
    "version": 1,
    "is_preview": false
}
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `session_id` | Yes | Session ID to load results for |
| `version` | No | Config version number (defaults to latest) |
| `is_preview` | No | `false` = full data only, `true` = preview only, omit = auto-detect (prefers full) |

**Response:**
```json
{
    "success": true,
    "table_metadata": {
        "columns": [...],
        "rows": [...],
        "general_notes": "...",
        "is_transposed": true
    },
    "table_name": "Validation Results (2024-01-24)",
    "clean_table_name": "Q4 Financial Results",
    "session_id": "session_20240124_abc123",
    "version": 1,
    "is_full_validation": true,
    "enhanced_download_url": "https://s3.../presigned-excel-url",
    "json_download_url": "https://s3.../presigned-json-url"
}
```

#### Action: `getDemoData`

Public endpoint (no auth required). Loads demo table from `demos/interactive_tables/{name}/`.

**Request:**
```json
{
    "action": "getDemoData",
    "table_name": "q4-financial-results-a1b2c3"
}
```

**Response:**
```json
{
    "success": true,
    "table_metadata": { ... },
    "table_name": "q4-financial-results-a1b2c3",
    "clean_table_name": "Q4 Financial Results",
    "is_demo": true,
    "enhanced_download_url": "https://s3.../presigned-excel-url"
}
```

#### Action: `shareTable`

Protected endpoint. Copies validation results to the public demos folder.

**Request:**
```json
{
    "action": "shareTable",
    "session_id": "session_20240124_abc123",
    "version": 1
}
```

**Response:**
```json
{
    "success": true,
    "table_name": "q4-financial-results-a1b2c3",
    "share_url_path": "q4-financial-results-a1b2c3",
    "already_shared": false
}
```

Idempotent: if already shared for the same session, returns `already_shared: true` with the existing slug.

#### Action: `unshareTable`

Protected endpoint. Removes a shared demo table.

**Request:**
```json
{
    "action": "unshareTable",
    "session_id": "session_20240124_abc123",
    "table_name": "q4-financial-results-a1b2c3"
}
```

#### Action: `checkShareStatus`

Protected endpoint. Checks if a session is currently shared.

**Request:**
```json
{
    "action": "checkShareStatus",
    "session_id": "session_20240124_abc123"
}
```

**Response:**
```json
{
    "success": true,
    "is_shared": true,
    "table_name": "q4-financial-results-a1b2c3",
    "share_url_path": "q4-financial-results-a1b2c3"
}
```

#### Backend File: `viewer_data.py`

Location: `src/lambdas/interface/actions/viewer_data.py`

Key functions:
- `handle(request_data, context)` - Main handler
- `_find_latest_version(storage_manager, session_path)` - Find most recent config version (handles both `_results` and `_results-dev` folders)
- `_find_results_folder(bucket, standard_prefix, dev_prefix)` - Find results folder with `-dev` fallback
- `_load_json_from_s3(bucket, key)` - Load and parse JSON from S3
- `_find_excel_file(bucket, prefix)` - Locate enhanced Excel in results folder
- `_generate_presigned_url(bucket, key, filename)` - Create download URL

#### Backend File: `share_table.py`

Location: `src/lambdas/interface/actions/share_table.py`

Key functions:
- `handle(request_data, context)` - Share a table (copy to demos folder)
- `handle_unshare(request_data, context)` - Remove a shared demo
- `handle_check_share_status(request_data, context)` - Check if session is shared
- `_generate_demo_name(table_name, session_id)` - Create URL-safe slug
- `_find_shared_demo_for_session(bucket, session_id)` - Search demos by session hash (paginated)

#### Backend File: `demo_data.py`

Location: `src/lambdas/interface/actions/demo_data.py`

Key functions:
- `handle(request_data, context)` - Load demo table (public, no auth)

#### Data Loading Priority

The backend loads metadata with this priority:

1. **If `is_preview=false`**: Only try `table_metadata.json` (full validation)
2. **If `is_preview=true`**: Only try `preview_table_metadata.json` (preview)
3. **If `is_preview` omitted (auto-detect)**:
   - Try `table_metadata.json` first (full validation, all rows)
   - Fall back to `preview_table_metadata.json` (preview, 3 rows)

#### Folder Fallback

If the standard results folder doesn't exist, the backend falls back to the `-dev` folder:
- `v{N}_results/` (primary)
- `v{N}_results-dev/` (fallback)

### S3 Storage Structure

Results are stored in the unified S3 bucket:

```
hyperplexity-storage[-dev]/
├── results/
│   └── {domain}/
│       └── {email_prefix}/
│           └── {session_id}/
│               └── v{version}_results/
│                   ├── table_metadata.json          # Full validation (all rows)
│                   ├── preview_table_metadata.json  # Preview (3 rows)
│                   ├── {filename}_enhanced.xlsx
│                   └── ...
└── demos/
    └── interactive_tables/
        └── {demo-slug}/
            ├── table_metadata.json      # Copied from session (with updated table_name)
            ├── {filename}_enhanced.xlsx  # Copied from session
            └── info.json                # Provenance metadata
```

#### Demo `info.json` Schema

```json
{
    "display_name": "Q4 Financial Results",
    "source_session_id": "session_20240124_abc123",
    "source_email_hash": "a1b2c3d4e5f6g7h8",
    "source_version": 1,
    "shared_at": "2024-01-24T18:59:05Z",
    "original_filename": "Q4_Financial_Results.xlsx"
}
```

| File | Created By | Rows |
|------|------------|------|
| `table_metadata.json` | Full validation completion | All rows |
| `preview_table_metadata.json` | Preview completion | First 3 rows |

## Table Metadata Schema

The `table_metadata` object structure:

```javascript
{
    "table_name": "Clinical Trials Analysis",  // Display name from session info
    "columns": [
        {
            "name": "Column Name",
            "importance": "HIGH|MEDIUM|LOW|ID",
            "description": "Column description",
            "notes": "Additional notes"
        }
    ],
    "rows": [
        {
            "row_key": "row_1",
            "cells": {
                "Column Name": {
                    "display_value": "Short value",
                    "full_value": "Complete value with details",
                    "confidence": "HIGH|MEDIUM|LOW|ID",
                    "comment": {
                        "validator_explanation": "Why this confidence",
                        "key_citation": "Source reference",
                        "original_value": "Value before validation",
                        "original_confidence": "Previous confidence"
                    }
                }
            }
        }
    ],
    "general_notes": "Table-level methodology and notes",
    "is_transposed": true
}
```

## Programmatic Usage

### After Validation Completes

```javascript
// Called when full validation finishes
showFullValidationResults({
    table_name: 'My Validation',
    row_count: 50,
    table_metadata: validationResult.table_metadata,
    enhanced_download_url: validationResult.enhanced_download_url
});
```

### Custom Viewer Card

```javascript
// Create viewer with pre-loaded data
const { cardId } = createResultsViewerCard({
    title: 'Custom Results',
    subtitle: 'From API response',
    tableMetadata: myTableMetadata,
    downloadUrl: myDownloadUrl
});

// Or create empty and populate later
const { cardId } = createResultsViewerCard({
    title: 'Loading...'
});

// Then populate
displayResultsInCard(cardId, {
    table_metadata: fetchedMetadata,
    enhanced_download_url: fetchedUrl,
    json_download_url: fetchedJsonUrl
});
```

## Local Development

### Test File

Use `frontend/viewer-test.html` for local testing:

```bash
cd frontend
python3 -m http.server 8000
# Open: http://localhost:8000/viewer-test.html
```

The test file:
- Loads real data from `preview_table_metadata.json` if available
- Falls back to mock data for basic testing
- Provides buttons to test different viewer functions
- Preserves your real email in localStorage (restores on page leave)

### Testing with Full Build

```bash
cd frontend
python3 -m http.server 8000
# Open: http://localhost:8000/Hyperplexity_FullScript_Temp-dev.html?mode=viewer&session=YOUR_SESSION_ID
```

Note: Requires valid session ID and matching email validation.

### Testing Demo Mode

```
# Public demo (no auth required)
?demo=q4-financial-results-a1b2c3
```

### Local JSON File Testing

```
?mode=viewer&path=preview_table_metadata.json
```

This loads directly from a local file without API calls (useful for UI development).

## Troubleshooting

### "Table metadata not found for this session"

1. **Wrong email**: Ensure you're validated with the same email that owns the session
2. **Wrong bucket**: Check `S3_UNIFIED_BUCKET` environment variable matches where data is stored
3. **Session doesn't exist**: Verify session ID is correct
4. **No results yet**: Validation may not have completed
5. **Full validation not run**: If requesting full data (`is_preview: false`), ensure full validation completed (not just preview)

### "No results folder found for this session"

1. Check both `v{N}_results/` and `v{N}_results-dev/` folders exist
2. Verify the version number is correct

### "Whoops - this table might never have existed..."

The demo table was either never shared or has been unshared by its owner.

### "Missing Parameters"

Ensure URL includes either `session` or `path` parameter:
```
?mode=viewer&session=session_xxx  ✓
?mode=viewer                      ✗
```

### Download Button Not Working

1. Check browser console for errors
2. Verify presigned URLs are being generated (check API response)
3. For JSON, client-side blob download should work even without API URL

### Share Button Issues

1. **Only full validations can be shared** - preview-only sessions will show an error
2. **Session ownership required** - you must own the session to share/unshare
3. **Clipboard requires HTTPS** - on HTTP, the link is shown instead of auto-copied

## Related Files

| File | Purpose |
|------|---------|
| `frontend/src/js/12-validation.js` | Full validation card with interactive table and Share button |
| `frontend/src/js/13-results.js` | Preview card with interactive table |
| `frontend/src/js/18-viewer-mode.js` | Standalone viewer, demo mode, share/unshare logic |
| `frontend/src/js/16-interactive-table.js` | Table rendering component |
| `frontend/src/js/00-config.js` | Mode detection (`detectPageType`, `getViewerParams`, `getDemoParams`) |
| `frontend/src/js/99-init.js` | Initialization routing |
| `frontend/viewer-test.html` | Local development test page |
| `src/lambdas/interface/actions/viewer_data.py` | Backend API handler for authenticated viewer |
| `src/lambdas/interface/actions/demo_data.py` | Backend API handler for public demos |
| `src/lambdas/interface/actions/share_table.py` | Backend share/unshare/check-status handlers |
| `src/lambdas/interface/handlers/background_handler.py` | Generates table_metadata.json on validation completion |
| `src/lambdas/interface/handlers/http_handler.py` | API routing |
