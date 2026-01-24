# Interactive Results Viewer

The Interactive Results Viewer provides a standalone way to view validation results with an interactive table interface. Users can access results via URL, explore data with hover tooltips and click-through modals, and download results in Excel or JSON format.

## Overview

The viewer can be used in two ways:

1. **Standalone Mode** - Access via URL with session parameters
2. **Embedded Card** - Called programmatically within the app after validation completes

## URL Parameters

### Standalone Viewer URL

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

### Examples

```
# View specific session results
?mode=viewer&session=session_20240124_185905_abc123

# View specific version
?mode=viewer&session=session_20240124_185905_abc123&version=2

# Local testing with JSON file
?mode=viewer&path=preview_table_metadata.json
```

## Authentication

The viewer requires email validation before displaying results. This ensures users can only access their own validation results.

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
| Download Excel | `.xlsx` | Full enhanced Excel with formatting, comments, and metadata |
| Download JSON | `.json` | Raw table_metadata for programmatic use or archival |

## Architecture

### Frontend Components

#### `18-viewer-mode.js`

Main viewer module with these functions:

| Function | Description |
|----------|-------------|
| `initViewerMode()` | Entry point when `mode=viewer` detected |
| `loadAndDisplayResults(params)` | Fetches data from API and renders |
| `createResultsViewerCard(options)` | Creates viewer card (can be called from anywhere) |
| `displayResultsInCard(cardId, data)` | Renders table and download buttons |
| `showFullValidationResults(data)` | Convenience function for post-validation display |
| `downloadJsonMetadata(metadata, button)` | Client-side JSON download fallback |

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
    "email": "user@example.com",
    "session_id": "session_20240124_abc123",
    "version": 1
}
```

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
    "session_id": "session_20240124_abc123",
    "version": 1,
    "enhanced_download_url": "https://s3.../presigned-excel-url",
    "json_download_url": "https://s3.../presigned-json-url"
}
```

**Error Response:**
```json
{
    "success": false,
    "error": "Table metadata not found for this session"
}
```

#### Backend File: `viewer_data.py`

Location: `src/lambdas/interface/actions/viewer_data.py`

Key functions:
- `handle(request_data, context)` - Main handler
- `_find_latest_version(storage_manager, session_path)` - Find most recent config version
- `_load_json_from_s3(bucket, key)` - Load and parse JSON from S3
- `_find_excel_file(bucket, prefix)` - Locate enhanced Excel in results folder
- `_generate_presigned_url(bucket, key, filename)` - Create download URL

### S3 Storage Structure

Results are stored in the unified S3 bucket:

```
hyperplexity-storage[-dev]/
└── results/
    └── {domain}/
        └── {email_prefix}/
            └── {session_id}/
                └── v{version}_results/
                    ├── preview_table_metadata.json
                    ├── {filename}_enhanced.xlsx
                    └── ...
```

## Table Metadata Schema

The `table_metadata` object structure:

```javascript
{
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

### "Missing Parameters"

Ensure URL includes either `session` or `path` parameter:
```
?mode=viewer&session=session_xxx  ✓
?mode=viewer                      ✗
```

### Download Button Not Working

1. Check browser console for errors
2. Verify presigned URLs are being generated (check API response)
3. For JSON, client-side fallback should work even without API URL

## Related Files

| File | Purpose |
|------|---------|
| `frontend/src/js/18-viewer-mode.js` | Viewer mode frontend logic |
| `frontend/src/js/16-interactive-table.js` | Table rendering component |
| `frontend/src/js/00-config.js` | Mode detection (`detectPageType`, `getViewerParams`) |
| `frontend/src/js/99-init.js` | Initialization routing |
| `frontend/viewer-test.html` | Local development test page |
| `src/lambdas/interface/actions/viewer_data.py` | Backend API handler |
| `src/lambdas/interface/handlers/http_handler.py` | API routing |
