# Interactive Table Preview Implementation Instructions

## Overview
Enhance the markdown table preview with interactive cells that show full values and comments on hover/click, while adding a frozen first column for better navigation.

## Requirements
1. **JSON Metadata**: Save cell values + comments (same as Excel comments) when generating previews
2. **Interactive Table**: Replace markdown table with custom HTML table with hover tooltips and click-to-expand
3. **Frozen Column**: First column (column names in transposed view) stays fixed during horizontal scroll
4. **Clean Design**: Minimal UI, emojis OK, preserve current clarity

---

## Implementation Details

### Phase 1: Backend - Generate Table Metadata JSON

**File: `src/shared/excel_report_qc_unified.py`**

Add new function `generate_table_preview_metadata()` after line ~1089 that extracts the same comment data logic from lines 946-1079.

```python
def generate_table_preview_metadata(
    rows_data: list,
    headers: list,
    validation_results: dict,
    qc_results: dict,
    config_data: dict,
    preview_row_count: int = 3
) -> dict:
    """
    Generate JSON metadata for interactive table preview.
    Returns same cell comments/metadata that would go into Excel comments.

    Structure:
    {
        "columns": [{"name": str, "importance": str, "description": str}],
        "rows": [{
            "row_key": str,
            "cells": {
                "ColumnName": {
                    "display_value": str,    # Truncated for table display (50 chars)
                    "full_value": str,       # Complete value
                    "confidence": str,       # HIGH/MEDIUM/LOW/ID
                    "comment": {
                        "original_value": str,
                        "original_confidence": str,
                        "validator_explanation": str,
                        "qc_reasoning": str,
                        "key_citation": str,
                        "sources": [{"id": int, "title": str, "url": str, "snippet": str}]
                    }
                }
            }
        }],
        "is_transposed": True
    }
    """
    # Extract column metadata from config_data['validation_targets']
    columns = []
    for target in config_data.get('validation_targets', []):
        columns.append({
            'name': target.get('column_name', ''),
            'importance': target.get('importance', ''),
            'description': target.get('description', '')
        })

    # Build rows with cell metadata
    rows = []
    for row_idx, row_data in enumerate(rows_data[:preview_row_count]):
        row_key = generate_row_key(row_data, config_data)  # Use existing row key logic
        row_validation_data = validation_results.get(row_key, {})
        row_qc_data = qc_results.get(row_key, {}) if qc_results else {}

        cells = {}
        for col in columns:
            col_name = col['name']
            full_value = str(row_data.get(col_name, ''))
            display_value = full_value[:50] + '...' if len(full_value) > 50 else full_value

            # Build comment using same logic as lines 946-1079
            comment = build_cell_comment(
                col_name, row_data, row_validation_data, row_qc_data
            )

            cells[col_name] = {
                'display_value': display_value,
                'full_value': full_value,
                'confidence': get_cell_confidence(col_name, row_validation_data, row_qc_data),
                'comment': comment
            }

        rows.append({
            'row_key': row_key,
            'cells': cells
        })

    return {
        'columns': columns,
        'rows': rows,
        'is_transposed': True
    }


def build_cell_comment(col_name, row_data, row_validation_data, row_qc_data):
    """
    Build cell comment dict using same logic as Excel comment building (lines 946-1079).
    """
    comment = {}

    if col_name not in row_validation_data:
        return comment

    field_data = row_validation_data[col_name]
    if not isinstance(field_data, dict):
        return comment

    original_value = row_data.get(col_name, '')
    validated_value = field_data.get('value', '')

    # Original value and confidence
    comment['original_value'] = original_value
    original_confidence = field_data.get('original_confidence', '')

    # Check for QC-adjusted confidence
    if row_qc_data and col_name in row_qc_data:
        field_qc_data = row_qc_data[col_name]
        if isinstance(field_qc_data, dict):
            qc_original_confidence = field_qc_data.get('qc_original_confidence')
            if qc_original_confidence:
                original_confidence = qc_original_confidence

    comment['original_confidence'] = original_confidence

    # Validator explanation
    explanation = field_data.get('explanation', '')
    if explanation:
        comment['validator_explanation'] = explanation

    # QC reasoning
    if row_qc_data and col_name in row_qc_data:
        field_qc_data = row_qc_data[col_name]
        if isinstance(field_qc_data, dict):
            qc_entry = field_qc_data.get('qc_entry', '')
            qc_reasoning = field_qc_data.get('qc_reasoning', '')
            qc_overrode = str(qc_entry).strip() != str(validated_value).strip() if qc_entry else False
            if qc_reasoning:
                if qc_overrode:
                    comment['qc_reasoning'] = f'(Validation Override) {qc_reasoning}'
                else:
                    comment['qc_reasoning'] = qc_reasoning

    # Key citation
    key_citation = None
    if row_qc_data and col_name in row_qc_data:
        field_qc_data = row_qc_data[col_name]
        if isinstance(field_qc_data, dict):
            qc_key_citation = field_qc_data.get('key_citation', '')
            if qc_key_citation:
                key_citation = qc_key_citation

    if not key_citation:
        citations = field_data.get('citations', [])
        if citations:
            first_citation = citations[0]
            cite_text = first_citation.get('title', 'Source')
            cite_url = first_citation.get('url', '')
            cite_snippet = first_citation.get('cited_text', '')
            if cite_snippet and len(cite_snippet) > 150:
                cite_snippet = cite_snippet[:150] + '...'
            key_citation = cite_text
            if cite_snippet:
                key_citation += f' - {cite_snippet}'
            if cite_url:
                key_citation += f' ({cite_url})'

    if key_citation:
        comment['key_citation'] = key_citation

    # Sources
    sources = []
    citations = field_data.get('citations', [])
    for i, citation in enumerate(citations, 1):
        sources.append({
            'id': i,
            'title': citation.get('title', 'Untitled'),
            'url': citation.get('url', ''),
            'snippet': citation.get('cited_text', ''),
            'confidence': citation.get('p', '')
        })

    # QC sources
    if row_qc_data and col_name in row_qc_data:
        field_qc_data = row_qc_data[col_name]
        if isinstance(field_qc_data, dict):
            qc_sources = field_qc_data.get('qc_sources', [])
            for i, qc_source in enumerate(qc_sources, 1):
                if isinstance(qc_source, str):
                    sources.append({'id': f'QC{i}', 'title': 'QC Source', 'url': qc_source, 'snippet': ''})
                elif isinstance(qc_source, dict):
                    sources.append({
                        'id': f'QC{i}',
                        'title': qc_source.get('title', 'QC Source'),
                        'url': qc_source.get('url', ''),
                        'snippet': qc_source.get('cited_text', ''),
                        'confidence': qc_source.get('p', '')
                    })

    if sources:
        comment['sources'] = sources

    return comment
```

**File: `src/lambdas/interface/handlers/background_handler.py`**

Around line 2164, after `markdown_table = create_markdown_table_from_results(...)`:
```python
from shared.excel_report_qc_unified import generate_table_preview_metadata

table_metadata = generate_table_preview_metadata(
    rows_data=rows_data,
    headers=headers,
    validation_results=real_results,
    qc_results=None,  # Already merged
    config_data=config_data,
    preview_row_count=3
)
```

Add `table_metadata` to `frontend_payload` around line 2745:
```python
frontend_payload = {
    "markdown_table": preview_payload.get("markdown_table", ""),
    "table_metadata": table_metadata,  # NEW
    "enhanced_download_url": preview_payload.get("enhanced_download_url"),
    # ... rest unchanged
}
```

---

### Phase 2: Frontend - Interactive Table Component

**File: `frontend/src/js/13-results.js`**

Add these functions after line 51:

```javascript
/**
 * Render an interactive table with frozen first column and tooltips
 */
function renderInteractiveTable(tableMetadata) {
    if (!tableMetadata || !tableMetadata.rows || tableMetadata.rows.length === 0) {
        return null;
    }

    const { columns, rows } = tableMetadata;

    let html = '<div class="interactive-table-container">';
    html += '<table class="interactive-table">';

    // Transposed format: columns as rows, data rows as columns
    // Header row: Column | Row 1 | Row 2 | Row 3
    html += '<thead><tr>';
    html += '<th class="sticky-column">Column</th>';
    rows.forEach((_, i) => {
        html += `<th>Row ${i + 1}</th>`;
    });
    html += '</tr></thead>';

    // Data rows: one row per column
    html += '<tbody>';
    columns.forEach(col => {
        const isIdColumn = col.importance && col.importance.toUpperCase() === 'ID';
        html += '<tr>';
        html += `<td class="sticky-column ${isIdColumn ? 'id-column' : ''}">`;
        html += `${isIdColumn ? '🔵 ' : ''}<strong>${escapeHtml(col.name)}</strong>`;
        html += '</td>';

        rows.forEach(row => {
            const cellData = row.cells[col.name] || {};
            const confidence = (cellData.confidence || '').toUpperCase();
            const displayValue = cellData.display_value || '';
            const fullValue = cellData.full_value || displayValue;
            const comment = cellData.comment || {};

            // Build tooltip content
            const tooltipContent = buildTooltipContent(comment, fullValue, displayValue);

            // Determine confidence class
            let confidenceClass = '';
            if (confidence === 'HIGH') confidenceClass = 'confidence-high';
            else if (confidence === 'MEDIUM') confidenceClass = 'confidence-medium';
            else if (confidence === 'LOW') confidenceClass = 'confidence-low';
            else if (confidence === 'ID') confidenceClass = 'confidence-id';

            html += `<td
                class="table-cell ${confidenceClass}"
                ${tooltipContent ? `data-tooltip="${escapeHtml(tooltipContent)}"` : ''}
                data-cell-data='${JSON.stringify(cellData).replace(/'/g, "&#39;")}'
                onclick="showCellDetailModal(this)"
            >`;
            html += `<span class="cell-value">${escapeHtml(displayValue)}</span>`;
            if (fullValue.length > displayValue.length) {
                html += '<span class="truncated-indicator">...</span>';
            }
            html += '</td>';
        });

        html += '</tr>';
    });
    html += '</tbody>';

    html += '</table></div>';
    return html;
}

function buildTooltipContent(comment, fullValue, displayValue) {
    let parts = [];

    // Show full value if truncated
    if (fullValue && fullValue.length > displayValue.length) {
        parts.push(`Full: ${fullValue.substring(0, 200)}${fullValue.length > 200 ? '...' : ''}`);
    }

    if (comment.original_value !== undefined && comment.original_value !== '') {
        const conf = comment.original_confidence ? ` (${comment.original_confidence})` : '';
        parts.push(`Original: ${comment.original_value}${conf}`);
    }

    if (comment.validator_explanation) {
        const explanation = comment.validator_explanation.length > 100
            ? comment.validator_explanation.substring(0, 100) + '...'
            : comment.validator_explanation;
        parts.push(`Reason: ${explanation}`);
    }

    if (comment.key_citation) {
        const citation = comment.key_citation.length > 80
            ? comment.key_citation.substring(0, 80) + '...'
            : comment.key_citation;
        parts.push(`Source: ${citation}`);
    }

    return parts.join(' | ');
}

function showCellDetailModal(cellElement) {
    const cellData = JSON.parse(cellElement.dataset.cellData || '{}');
    const comment = cellData.comment || {};

    let modalContent = `
        <div class="cell-detail-modal">
            <div class="cell-detail-header">
                <h3>📋 Cell Details</h3>
                <button class="modal-close" onclick="closeCellDetailModal()">&times;</button>
            </div>

            <div class="detail-section">
                <label>Current Value</label>
                <p class="detail-value">${escapeHtml(cellData.full_value || cellData.display_value || '-')}</p>
            </div>

            ${comment.original_value !== undefined ? `
            <div class="detail-section">
                <label>Original Value</label>
                <p class="detail-value">${escapeHtml(comment.original_value)}
                    ${comment.original_confidence ? `<span class="confidence-badge">${comment.original_confidence}</span>` : ''}</p>
            </div>
            ` : ''}

            ${comment.validator_explanation ? `
            <div class="detail-section">
                <label>🔍 Validator Explanation</label>
                <p class="detail-value">${escapeHtml(comment.validator_explanation)}</p>
            </div>
            ` : ''}

            ${comment.qc_reasoning ? `
            <div class="detail-section">
                <label>✅ QC Reasoning</label>
                <p class="detail-value">${escapeHtml(comment.qc_reasoning)}</p>
            </div>
            ` : ''}

            ${comment.key_citation ? `
            <div class="detail-section">
                <label>🔗 Key Citation</label>
                <p class="detail-value">${escapeHtml(comment.key_citation)}</p>
            </div>
            ` : ''}

            ${comment.sources && comment.sources.length > 0 ? `
            <div class="detail-section">
                <label>📚 Sources</label>
                <ul class="sources-list">
                    ${comment.sources.map(s => `
                        <li>
                            <span class="source-id">[${s.id}]</span>
                            ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank">${escapeHtml(s.title)}</a>` : escapeHtml(s.title)}
                            ${s.snippet ? `<br><small class="source-snippet">"${escapeHtml(s.snippet.substring(0, 150))}${s.snippet.length > 150 ? '...' : ''}"</small>` : ''}
                        </li>
                    `).join('')}
                </ul>
            </div>
            ` : ''}
        </div>
    `;

    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className = 'cell-detail-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) closeCellDetailModal(); };
    overlay.innerHTML = modalContent;
    document.body.appendChild(overlay);

    // Add escape key handler
    document.addEventListener('keydown', handleModalEscape);
}

function closeCellDetailModal() {
    const overlay = document.querySelector('.cell-detail-overlay');
    if (overlay) overlay.remove();
    document.removeEventListener('keydown', handleModalEscape);
}

function handleModalEscape(e) {
    if (e.key === 'Escape') closeCellDetailModal();
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}
```

**Modify `showPreviewResults()` at line 47:**

Replace:
```javascript
previewContent.innerHTML = headerHtml + renderMarkdown(previewData.markdown_table);
```

With:
```javascript
if (previewData.table_metadata) {
    const interactiveTable = renderInteractiveTable(previewData.table_metadata);
    previewContent.innerHTML = headerHtml + (interactiveTable || renderMarkdown(previewData.markdown_table));
} else {
    previewContent.innerHTML = headerHtml + renderMarkdown(previewData.markdown_table);
}
```

---

### Phase 3: CSS Styling

**File: `frontend/src/styles/07-tables.css`**

Add after line 54:

```css
/* ========================================
 * Interactive Table Styles
 * ======================================== */

/* Container with horizontal scroll */
.interactive-table-container {
    overflow-x: auto;
    max-width: 100%;
    margin: 1rem 0;
    border: 1px solid #e0e0e0;
    border-radius: var(--border-radius);
    background: #fff;
}

/* Main table */
.interactive-table {
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    min-width: 500px;
    font-size: var(--font-size-small);
}

.interactive-table th,
.interactive-table td {
    padding: 0.6rem 0.8rem;
    border-bottom: 1px solid #eee;
    border-right: 1px solid #eee;
    text-align: left;
    vertical-align: top;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
}

.interactive-table th {
    background: #f8f9fa;
    font-weight: 600;
    color: var(--text-color);
    position: sticky;
    top: 0;
    z-index: 2;
}

/* Frozen first column */
.interactive-table .sticky-column {
    position: sticky;
    left: 0;
    background: #fff;
    z-index: 1;
    min-width: 150px;
    max-width: 200px;
    box-shadow: 2px 0 4px rgba(0,0,0,0.06);
    border-right: 2px solid #e0e0e0;
}

.interactive-table th.sticky-column {
    z-index: 3;
    background: #f8f9fa;
}

/* ID column styling */
.interactive-table .id-column {
    color: #1565c0;
}

/* Confidence colors */
.interactive-table .confidence-high {
    background-color: #e8f5e9;
}

.interactive-table .confidence-medium {
    background-color: #fff8e1;
}

.interactive-table .confidence-low {
    background-color: #ffebee;
}

.interactive-table .confidence-id {
    background-color: #e3f2fd;
}

/* Cell hover and interaction */
.interactive-table .table-cell {
    position: relative;
    cursor: pointer;
    transition: background-color 0.15s ease;
}

.interactive-table .table-cell:hover {
    filter: brightness(0.95);
}

.truncated-indicator {
    color: #999;
    font-style: italic;
}

/* CSS Tooltips */
.interactive-table .table-cell[data-tooltip] {
    cursor: help;
}

.interactive-table .table-cell[data-tooltip]:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: #333;
    color: #fff;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.4;
    white-space: pre-wrap;
    max-width: 350px;
    min-width: 200px;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    pointer-events: none;
}

.interactive-table .table-cell[data-tooltip]:hover::before {
    content: '';
    position: absolute;
    bottom: calc(100% + 2px);
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-top-color: #333;
    z-index: 1000;
}

/* Cell Detail Modal */
.cell-detail-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 20px;
}

.cell-detail-modal {
    background: #fff;
    border-radius: 12px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}

.cell-detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid #eee;
    position: sticky;
    top: 0;
    background: #fff;
}

.cell-detail-header h3 {
    margin: 0;
    font-size: 1.1rem;
}

.modal-close {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #666;
    padding: 0;
    line-height: 1;
}

.modal-close:hover {
    color: #333;
}

.detail-section {
    padding: 12px 20px;
    border-bottom: 1px solid #f0f0f0;
}

.detail-section:last-child {
    border-bottom: none;
}

.detail-section label {
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #666;
    margin-bottom: 4px;
    font-weight: 600;
}

.detail-section .detail-value {
    margin: 0;
    color: var(--text-color);
    line-height: 1.5;
}

.confidence-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    margin-left: 8px;
    background: #e0e0e0;
}

.sources-list {
    margin: 8px 0 0 0;
    padding-left: 0;
    list-style: none;
}

.sources-list li {
    padding: 8px 0;
    border-bottom: 1px solid #f5f5f5;
}

.sources-list li:last-child {
    border-bottom: none;
}

.source-id {
    font-weight: 600;
    color: var(--secondary-color);
    margin-right: 4px;
}

.source-snippet {
    display: block;
    margin-top: 4px;
    color: #666;
    font-style: italic;
}
```

---

## Critical Files Reference

| Purpose | File Path | Key Lines |
|---------|-----------|-----------|
| Comment building logic (copy this) | `src/shared/excel_report_qc_unified.py` | 946-1079 |
| WebSocket payload construction | `src/lambdas/interface/handlers/background_handler.py` | 2745-2779 |
| Preview display function | `frontend/src/js/13-results.js` | 10-51 |
| Existing table styles | `frontend/src/styles/07-tables.css` | 1-54 |
| Markdown rendering reference | `frontend/src/js/05-chat.js` | 113-132 |

---

## Verification Steps

1. **Backend**: Run a preview validation and check WebSocket message contains `table_metadata`
2. **Frontend**: Verify table renders with frozen first column (scroll horizontally to test)
3. **Tooltips**: Hover over cells to see summary info
4. **Modal**: Click cells to see full details with sources
5. **Fallback**: Test that previews without `table_metadata` still render markdown
6. **Build**: Run `python3 frontend/build.py` to rebuild frontend

---

## Notes
- Emojis are OK for this UI (🔵 for ID columns, 📋 📚 🔍 ✅ 🔗 for modal sections)
- Pure CSS tooltips - no external library needed
- Backwards compatible with existing markdown preview
- Transposed table format preserved (columns as rows)
