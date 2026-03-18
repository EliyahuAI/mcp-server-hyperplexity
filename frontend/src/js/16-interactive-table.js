/* ========================================
 * 16-interactive-table.js - Modular Interactive Table Component
 *
 * Pure table rendering module for displaying validation results.
 * Can be used in preview cards, full results, and standalone viewers.
 * Does NOT include buttons - use card button system for actions.
 *
 * Dependencies: None (self-contained)
 * ======================================== */

/**
 * InteractiveTable - Modular table component for rendering validation data
 */
const InteractiveTable = (function() {
    'use strict';

    /* ========================================
     * State Variables
     * ======================================== */
    let tooltipElement = null;
    let tooltipTimeout = null;
    let hoverDelayTimeout = null;
    let currentHoverCell = null;
    let currentModalCell = null;
    let isTouchDevice = false;
    let navSettleTimeout = null;

    /* ========================================
     * Default Options
     * ======================================== */
    const defaultOptions = {
        showGeneralNotes: true,    // Show collapsible notes box
        showLegend: true,          // Show confidence color legend
        maxRows: null,             // Limit rows (null = all)
        infoBoxText: null,         // Blue info box text (shown after general notes)
    };

    /* ========================================
     * Utility Functions
     * ======================================== */

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    /**
     * Build tooltip content for cell hover
     */
    function buildTooltipContent(comment, fullValue, displayValue) {
        let parts = [];

        // Show full value if truncated
        if (fullValue && fullValue.length > displayValue.length) {
            const truncated = fullValue.substring(0, 200) + (fullValue.length > 200 ? '...' : '');
            parts.push(`<b>Full:</b> ${escapeHtml(truncated)}`);
        }

        if (comment.validator_explanation) {
            const explanation = comment.validator_explanation.length > 150
                ? comment.validator_explanation.substring(0, 150) + '...'
                : comment.validator_explanation;
            parts.push(`<b>Reason:</b> ${escapeHtml(explanation)}`);
        }

        if (parts.length > 0) {
            parts.push('<span class="tooltip-hint">Click for more</span>');
        }
        return parts.join('<br>');
    }

    /**
     * Build tooltip content for column headers
     */
    function buildColumnTooltip(description, notes) {
        let parts = [];

        if (description && description.trim()) {
            parts.push(`<b>Description:</b> ${escapeHtml(description)}`);
        }

        if (notes && notes.trim()) {
            parts.push(`<b>Notes:</b> ${escapeHtml(notes)}`);
        }

        return parts.join('<br>');
    }

    /* ========================================
     * Render Functions
     * ======================================== */

    /**
     * Render an interactive table from metadata
     * @param {Object} tableMetadata - Table metadata with columns, rows, general_notes
     * @param {Object} options - Rendering options
     * @returns {string} HTML string of the table
     */
    function render(tableMetadata, options = {}) {
        const opts = { ...defaultOptions, ...options };

        // Validate input
        if (!tableMetadata || !tableMetadata.rows || tableMetadata.rows.length === 0 ||
            !tableMetadata.columns || tableMetadata.columns.length === 0) {
            return '<p class="table-empty-message">No table data available.</p>';
        }

        const { columns, general_notes } = tableMetadata;
        let rows = tableMetadata.rows;

        // Apply row limit if specified
        if (opts.maxRows && opts.maxRows > 0) {
            rows = rows.slice(0, opts.maxRows);
        }

        let html = '';

        // General notes info box (collapsible if long)
        if (opts.showGeneralNotes && general_notes && general_notes.trim()) {
            const isLong = general_notes.length > 200;
            const uniqueId = 'general-notes-' + Date.now();
            html += `<div class="general-notes-box${isLong ? ' collapsible collapsed' : ''}" ${isLong ? `onclick="InteractiveTable.toggleGeneralNotes('${uniqueId}')"` : ''} id="${uniqueId}">
                <div class="general-notes-header">
                    <span class="general-notes-icon">📋</span>
                    <span class="general-notes-title">Configuration Notes</span>
                    ${isLong ? '<span class="general-notes-expand-hint">(click to expand)</span><span class="general-notes-toggle">▼</span>' : ''}
                </div>
                <div class="general-notes-content">${escapeHtml(general_notes)}</div>
            </div>`;
        }

        // Blue info box (after general notes)
        if (opts.infoBoxText) {
            html += `<div class="viewer-info-box">
                <span class="viewer-info-icon">ℹ</span>
                <span>${escapeHtml(opts.infoBoxText)}</span>
            </div>`;
        }

        // Color legend/key
        if (opts.showLegend) {
            html += `<div class="table-legend">
                <span class="legend-title">Confidence:</span>
                <span class="legend-item"><span class="legend-color confidence-high"></span> High</span>
                <span class="legend-item"><span class="legend-color confidence-medium"></span> Medium</span>
                <span class="legend-item"><span class="legend-color confidence-low"></span> Low</span>
                <span class="legend-item"><span class="legend-color confidence-id"></span> ID</span>
            </div>`;
        }

        // Auto-compute default: transposed when >5 columns (avoids horizontal overflow)
        if (tableMetadata.is_transposed === undefined || tableMetadata.is_transposed === null) {
            tableMetadata.is_transposed = columns.length > 5;
        }
        const transposed = tableMetadata.is_transposed !== false;
        html += `<div class="interactive-table-container${transposed ? '' : ' non-transposed'}">`;
        html += '<table class="interactive-table">';

        if (transposed) {
            // Transposed format: columns as rows, data rows as columns
            // Header row: Column | Row 1 | Row 2 | Row 3
            html += '<thead><tr>';
            html += '<th class="sticky-column" data-col-index="0">Column</th>';
            rows.forEach((_, i) => {
                html += `<th data-col-index="${i + 1}">Row ${i + 1}</th>`;
            });
            html += '</tr></thead>';

            // Data rows: one row per column
            html += '<tbody>';
            columns.forEach(col => {
                // Both ID and IGNORED columns should show as ID style
                const importance = col.importance ? col.importance.toUpperCase() : '';
                const isIdColumn = importance === 'ID' || importance === 'IGNORED';

                // Build column header tooltip from description and notes
                const colTooltip = buildColumnTooltip(col.description, col.notes);
                const hasTooltip = colTooltip && colTooltip.length > 0;

                html += `<tr${isIdColumn ? ' class="id-row"' : ''}>`;
                html += `<td class="sticky-column ${isIdColumn ? 'id-column' : ''}${hasTooltip ? ' has-column-info' : ''}" data-col-index="0"`;
                if (hasTooltip) {
                    html += ` data-tooltip-html="${colTooltip.replace(/"/g, '&quot;')}"`;
                    html += ` onmouseenter="InteractiveTable.showTooltip(event, this)"`;
                    html += ` onmouseleave="InteractiveTable.hideTooltip()"`;
                }
                html += '>';
                html += `<strong>${escapeHtml(col.name)}</strong>`;
                html += '</td>';

                rows.forEach((row, colIdx) => {
                    const cellData = row.cells[col.name] || {};
                    const confidence = (cellData.confidence || '').toUpperCase();
                    const displayValue = cellData.display_value || '';
                    const fullValue = cellData.full_value || displayValue;
                    const comment = cellData.comment || {};

                    // Add column name and row ID info to cell data for modal display
                    // Get ID values from cells marked as ID columns
                    const idColumns = columns.filter(c => c.importance && c.importance.toUpperCase() === 'ID');
                    let rowIdValues = '';
                    if (idColumns.length > 0) {
                        // Use explicitly marked ID columns
                        rowIdValues = idColumns.map(idCol => row.cells[idCol.name]?.display_value || '').filter(v => v).join(', ');
                    } else {
                        // Fallback: use first 2 columns as ID when none are marked
                        const fallbackIdColumns = columns.slice(0, 2);
                        rowIdValues = fallbackIdColumns.map(idCol => row.cells[idCol.name]?.display_value || '').filter(v => v).join(', ');
                    }
                    cellData._columnName = col.name;
                    cellData._rowId = rowIdValues || `Row ${colIdx + 1}`;

                    // Build tooltip content
                    const tooltipContent = buildTooltipContent(comment, fullValue, displayValue);

                    // Determine confidence class
                    let confidenceClass = '';
                    if (confidence === 'HIGH') confidenceClass = 'confidence-high';
                    else if (confidence === 'MEDIUM') confidenceClass = 'confidence-medium';
                    else if (confidence === 'LOW') confidenceClass = 'confidence-low';
                    else if (confidence === 'ID') confidenceClass = 'confidence-id';

                    // Properly escape JSON for HTML attribute
                    const cellDataJson = JSON.stringify(cellData)
                        .replace(/&/g, '&amp;')
                        .replace(/'/g, '&#39;')
                        .replace(/"/g, '&quot;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');

                    html += `<td
                        class="table-cell ${confidenceClass}"
                        data-col-index="${colIdx + 1}"
                        data-tooltip-html="${tooltipContent ? tooltipContent.replace(/"/g, '&quot;') : ''}"
                        data-cell-data="${cellDataJson}"
                        onclick="InteractiveTable.showCellModal(this)"
                        onmouseenter="InteractiveTable.showTooltip(event, this); InteractiveTable.highlightColumn(${colIdx + 1})"
                        onmouseleave="InteractiveTable.hideTooltip(); InteractiveTable.clearColumnHighlight()"
                    >`;
                    html += `<span class="cell-value">${escapeHtml(displayValue)}</span>`;
                    html += '</td>';
                });

                html += '</tr>';
            });
            html += '</tbody>';
        } else {
            // Standard (non-transposed) format: rows as rows, columns as columns
            // Header row: Col1 | Col2 | Col3 | ...
            // Sticky column = first ID-typed column, or col 0 if none
            const stickyColIdx = 0;

            html += '<thead><tr>';
            columns.forEach((col, i) => {
                const colTooltip = buildColumnTooltip(col.description, col.notes);
                const hasTooltip = colTooltip && colTooltip.length > 0;
                const thClasses = [];
                if (i === stickyColIdx) thClasses.push('sticky-column');
                if (hasTooltip) thClasses.push('has-column-info');
                const classAttr = thClasses.length ? ` class="${thClasses.join(' ')}"` : '';
                html += `<th${classAttr} data-col-index="${i}"`;
                if (hasTooltip) {
                    html += ` data-tooltip-html="${colTooltip.replace(/"/g, '&quot;')}"`;
                    html += ` onmouseenter="InteractiveTable.showTooltip(event, this)"`;
                    html += ` onmouseleave="InteractiveTable.hideTooltip()"`;
                }
                html += `>${escapeHtml(col.name)}</th>`;
            });
            html += '</tr></thead>';

            // Data rows: one row per data row
            html += '<tbody>';
            const idColumnsNT = columns.filter(c => c.importance && c.importance.toUpperCase() === 'ID');
            rows.forEach((row, rowIdx) => {
                /* stickyColIdx defined in thead block above */
                // Compute row ID for modal display
                let rowIdValues = '';
                if (idColumnsNT.length > 0) {
                    rowIdValues = idColumnsNT.map(idCol => row.cells[idCol.name]?.display_value || '').filter(v => v).join(', ');
                } else {
                    const fallbackIdColumns = columns.slice(0, 2);
                    rowIdValues = fallbackIdColumns.map(idCol => row.cells[idCol.name]?.display_value || '').filter(v => v).join(', ');
                }
                const rowLabel = rowIdValues || `Row ${rowIdx + 1}`;

                html += '<tr>';
                columns.forEach((col, colIdx) => {
                    const cellData = { ...(row.cells[col.name] || {}) };
                    const confidence = (cellData.confidence || '').toUpperCase();
                    const displayValue = cellData.display_value || '';
                    const fullValue = cellData.full_value || displayValue;
                    const comment = cellData.comment || {};

                    cellData._columnName = col.name;
                    cellData._rowId = rowLabel;

                    const tooltipContent = buildTooltipContent(comment, fullValue, displayValue);

                    let confidenceClass = '';
                    if (confidence === 'HIGH') confidenceClass = 'confidence-high';
                    else if (confidence === 'MEDIUM') confidenceClass = 'confidence-medium';
                    else if (confidence === 'LOW') confidenceClass = 'confidence-low';
                    else if (confidence === 'ID') confidenceClass = 'confidence-id';

                    const cellDataJson = JSON.stringify(cellData)
                        .replace(/&/g, '&amp;')
                        .replace(/'/g, '&#39;')
                        .replace(/"/g, '&quot;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');

                    const importance = (col.importance || '').toUpperCase();
                    const isIdCol = importance === 'ID' || importance === 'IGNORED';
                    const tdClasses = ['table-cell'];
                    if (colIdx === stickyColIdx) tdClasses.unshift('sticky-column');
                    if (isIdCol) tdClasses.push('id-column');
                    if (confidenceClass) tdClasses.push(confidenceClass);

                    html += `<td
                        class="${tdClasses.join(' ')}"
                        data-col-index="${colIdx}"
                        data-tooltip-html="${tooltipContent ? tooltipContent.replace(/"/g, '&quot;') : ''}"
                        data-cell-data="${cellDataJson}"
                        onclick="InteractiveTable.showCellModal(this)"
                        onmouseenter="InteractiveTable.showTooltip(event, this); InteractiveTable.highlightColumn(${colIdx})"
                        onmouseleave="InteractiveTable.hideTooltip(); InteractiveTable.clearColumnHighlight()"
                    >`;
                    html += `<span class="cell-value">${escapeHtml(displayValue)}</span>`;
                    html += '</td>';
                });
                html += '</tr>';
            });
            html += '</tbody>';
        }

        html += '</table></div>';
        return html;
    }

    /**
     * Toggle transposed/standard layout and re-render the table in place.
     * @param {string} cardId - Card ID (table container is `${cardId}-table-container`)
     * @param {Object} metadata - Table metadata object (mutated in place)
     * @param {Object} [opts] - Render options (defaults to showGeneralNotes+showLegend)
     */
    function transposeInCard(cardId, metadata, opts) {
        if (!metadata) return null;
        metadata.is_transposed = metadata.is_transposed !== false ? false : true;
        const el = document.getElementById(`${cardId}-table-container`);
        if (!el) return null;
        el.innerHTML = render(metadata, opts || { showGeneralNotes: true, showLegend: true });
        // Update layout hint if present
        const hintEl = document.getElementById(`${cardId}-layout-hint`);
        if (hintEl) {
            hintEl.textContent = metadata.is_transposed
                ? 'Rows are shown as columns. Click Transpose to switch back to standard view.'
                : 'Hover cells for quick info, click for full details.';
        }
        return metadata.is_transposed;
    }

    /* ========================================
     * Helper: Convert Sample Rows to Metadata
     * ======================================== */

    /**
     * Convert sample rows (from AI generation) to table_metadata format
     * @param {Array} columns - Array of column objects {name, importance, description}
     * @param {Array} sampleRows - Array of row data objects
     * @param {number} maxRows - Maximum rows to include (default 3)
     * @returns {Object} Table metadata in standard format
     */
    function fromSampleRows(columns, sampleRows, maxRows = 3) {
        // Validate inputs - return empty metadata if invalid
        if (!Array.isArray(columns) || columns.length === 0) {
            console.warn('[InteractiveTable] fromSampleRows: columns is empty or not an array');
            return { columns: [], rows: [], is_transposed: true, general_notes: '' };
        }
        if (!Array.isArray(sampleRows) || sampleRows.length === 0) {
            console.warn('[InteractiveTable] fromSampleRows: sampleRows is empty or not an array');
            return { columns: [], rows: [], is_transposed: true, general_notes: '' };
        }

        return {
            columns: columns.map(col => ({
                name: col.name || (typeof col === 'string' ? col : String(col)),
                importance: col.importance || 'MEDIUM',
                description: col.description || ''
            })),
            rows: sampleRows.slice(0, maxRows).map((row, idx) => {
                // Handle null/undefined rows
                if (!row || typeof row !== 'object') {
                    return { row_key: `row_${idx + 1}`, cells: {} };
                }
                return {
                    row_key: `row_${idx + 1}`,
                    cells: Object.fromEntries(columns.map(col => {
                        const colName = col.name || (typeof col === 'string' ? col : String(col));
                        const value = String(row[colName] ?? '');
                        return [colName, {
                            display_value: value,  // Let CSS handle truncation
                            full_value: value,
                            confidence: (col.importance || '').toUpperCase() === 'ID' ? 'ID' : 'MEDIUM',
                            comment: {}
                        }];
                    }))
                };
            }),
            is_transposed: true,
            general_notes: ''
        };
    }

    /* ========================================
     * Event Handlers - Tooltips
     * ======================================== */

    /**
     * Show custom tooltip on hover
     */
    function showTooltip(event, cell) {
        const html = cell.dataset.tooltipHtml;

        // Track current cell and store event coords
        currentHoverCell = cell;
        const coords = { x: event.clientX, y: event.clientY };

        // Immediately show cell saturation and column highlights (skip for sticky column headers)
        // Note: Highlighting works even on touch devices, only the tooltip popup is disabled
        const colIndex = cell.dataset.colIndex;
        const isColumnHeader = colIndex === '0' || cell.classList.contains('sticky-column') || cell.closest('tr.id-row') !== null;

        if (!isColumnHeader) {
            cell.classList.add('cell-hover-active');
            if (colIndex) {
                const cells = document.querySelectorAll(`.interactive-table [data-col-index="${colIndex}"]`);
                cells.forEach(c => c.classList.add('column-highlight'));
            }
        }

        // Skip tooltip popup on touch devices (but highlighting above still works)
        if (isTouchDevice) return;

        if (!html) return;

        // Clear any pending timeouts
        if (tooltipTimeout) {
            clearTimeout(tooltipTimeout);
            tooltipTimeout = null;
        }
        if (hoverDelayTimeout) {
            clearTimeout(hoverDelayTimeout);
            hoverDelayTimeout = null;
        }

        // Delay showing tooltip by 300ms
        hoverDelayTimeout = setTimeout(() => {
            if (currentHoverCell !== cell) return;

            // Create tooltip if doesn't exist
            if (!tooltipElement) {
                tooltipElement = document.createElement('div');
                tooltipElement.className = 'custom-tooltip';
                document.body.appendChild(tooltipElement);
            }

            // Set content as HTML
            tooltipElement.innerHTML = html;
            tooltipElement.style.display = 'block';

            // Position near cursor
            const padding = 12;
            let x = coords.x + padding;
            let y = coords.y + padding;

            // Measure tooltip
            const rect = tooltipElement.getBoundingClientRect();

            // Keep on screen
            if (x + rect.width > window.innerWidth - padding) {
                x = coords.x - rect.width - padding;
            }
            if (y + rect.height > window.innerHeight - padding) {
                y = coords.y - rect.height - padding;
            }

            tooltipElement.style.left = x + 'px';
            tooltipElement.style.top = y + 'px';
        }, 300);
    }

    /**
     * Hide custom tooltip
     */
    function hideTooltip() {
        // Clear hover delay
        if (hoverDelayTimeout) {
            clearTimeout(hoverDelayTimeout);
            hoverDelayTimeout = null;
        }

        // Remove cell hover class
        if (currentHoverCell) {
            currentHoverCell.classList.remove('cell-hover-active');
        }
        currentHoverCell = null;

        // Clear column highlights
        const highlighted = document.querySelectorAll('.interactive-table .column-highlight');
        highlighted.forEach(cell => cell.classList.remove('column-highlight'));

        // Hide tooltip immediately
        if (tooltipElement) {
            tooltipElement.style.display = 'none';
        }
    }

    /**
     * Highlight a column
     */
    function highlightColumn(colIndex) {
        // Handled in showTooltip for compatibility
    }

    /**
     * Clear column highlight
     */
    function clearColumnHighlight() {
        // Handled in hideTooltip for compatibility
    }

    /* ========================================
     * Event Handlers - Modal
     * ======================================== */

    /**
     * Show cell detail modal
     */
    function showCellModal(cellElement, skipScroll = false, noAnimate = false) {
        // Track current cell for navigation
        currentModalCell = cellElement;

        // Determine navigation state
        const cells = getAllInteractiveCells();
        const currentIndex = cells.indexOf(cellElement);
        const hasPrev = currentIndex > 0;
        const hasNext = currentIndex < cells.length - 1;

        // Parse cell data JSON from data attribute
        // Note: Browser automatically unescapes HTML entities when reading from dataset,
        // so no manual unescaping is needed (and would cause issues with literal entity strings)
        const cellDataStr = cellElement.dataset.cellData || '{}';
        let cellData;
        try {
            cellData = JSON.parse(cellDataStr);
        } catch (e) {
            console.error('[InteractiveTable] Failed to parse cell data:', e, cellDataStr);
            cellData = { display_value: cellElement.textContent, comment: {} };
        }
        const comment = cellData.comment || {};

        // Determine confidence info
        const currentConfidence = (cellData.confidence || '').toUpperCase();

        // Get confidence class for styling
        const getConfidenceClass = (conf) => {
            if (conf === 'HIGH') return 'confidence-high';
            if (conf === 'MEDIUM') return 'confidence-medium';
            if (conf === 'LOW') return 'confidence-low';
            if (conf === 'ID') return 'confidence-id';
            return '';
        };

        // Format confidence text
        const formatConfidence = (conf) => {
            if (!conf) return '';
            if (conf === 'ID') return 'ID';
            return conf + ' CONFIDENCE';
        };

        // Format value with newlines preserved
        const formatValue = (val) => {
            if (!val) return '-';
            return escapeHtml(val).replace(/\n/g, '<br>');
        };

        // Determine if value was updated
        const currentValue = cellData.full_value || cellData.display_value || '-';
        const originalValue = comment.original_value;
        const originalConfidence = comment.original_confidence ? comment.original_confidence.toUpperCase() : '';

        // Check if updated - compare normalized values
        const normalizeValue = (v) => v === undefined || v === null ? '' : String(v).replace(/\s+/g, ' ').trim();
        const isUpdated = originalValue !== undefined && originalValue !== '' &&
                          normalizeValue(originalValue) !== normalizeValue(currentValue);

        const columnName = cellData._columnName || 'Unknown';
        const rowId = cellData._rowId || 'Unknown';

        let modalContent = `
            <div class="cell-detail-modal">
                <div class="cell-detail-header">
                    <div class="cell-detail-nav">
                        <button class="modal-nav-btn" onclick="InteractiveTable.navigatePrev()" ${!hasPrev ? 'disabled' : ''} title="Previous cell (←)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
                        </button>
                    </div>
                    <div class="cell-detail-title">
                        <span class="cell-detail-row-id">${escapeHtml(rowId)}</span>
                        <h3>${escapeHtml(columnName)}</h3>
                    </div>
                    <div class="cell-detail-actions">
                        <button class="modal-nav-btn" onclick="InteractiveTable.navigateNext()" ${!hasNext ? 'disabled' : ''} title="Next cell (→)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
                        </button>
                        <button class="modal-close" onclick="InteractiveTable.closeModal()">&times;</button>
                    </div>
                </div>

                <div class="detail-section">
                    <label>${isUpdated ? 'Updated Value' : 'Value'} ${currentConfidence ? `<span class="confidence-text ${getConfidenceClass(currentConfidence)}">${formatConfidence(currentConfidence)}</span>` : ''}</label>
                    <p class="detail-value">${formatValue(currentValue)}</p>
                </div>

                ${isUpdated ? `
                <div class="detail-section">
                    <label>Original Value ${originalConfidence ? `<span class="confidence-text ${getConfidenceClass(originalConfidence)}">${formatConfidence(originalConfidence)}</span>` : ''}</label>
                    <p class="detail-value">${formatValue(originalValue)}</p>
                </div>
                ` : ''}

                ${comment.validator_explanation ? `
                <div class="detail-section">
                    <label>🔍 Explanation</label>
                    <p class="detail-value">${escapeHtml(comment.validator_explanation)}</p>
                </div>
                ` : ''}

                ${comment.qc_reasoning ? `
                <div class="detail-section">
                    <label>✅ QC Reasoning</label>
                    <p class="detail-value">${escapeHtml(comment.qc_reasoning)}</p>
                </div>
                ` : ''}

                ${comment.sources && comment.sources.length > 0 ? `
                <div class="detail-section">
                    <label>📚 Sources</label>
                    <ul class="sources-list">
                        ${comment.sources.map((s, idx) => {
                            const snippetId = `snippet-${Date.now()}-${idx}`;
                            const isLongSnippet = s.snippet && s.snippet.length > 150;
                            const shortSnippet = isLongSnippet ? s.snippet.substring(0, 150) + '...' : s.snippet;

                            // Check if this source is the key citation
                            // Match by: [1] reference, title, or URL
                            let isKeyCitation = false;
                            if (comment.key_citation) {
                                const keyCite = comment.key_citation.trim();
                                // Check if it's a reference like "[1]"
                                const refMatch = keyCite.match(/^\[(\d+)\]$/);
                                if (refMatch && s.id == refMatch[1]) {
                                    isKeyCitation = true;
                                }
                                // Check if title is in key citation
                                else if (s.title && keyCite.includes(s.title)) {
                                    isKeyCitation = true;
                                }
                                // Check if URL is in key citation
                                else if (s.url && keyCite.includes(s.url)) {
                                    isKeyCitation = true;
                                }
                            }

                            return `
                            <li>
                                <span class="source-id">[${s.id}]</span>
                                ${isKeyCitation ? '<span class="key-citation-badge">KEY CITATION</span> ' : ''}
                                ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" class="source-link">${escapeHtml(s.title)}</a>` : `<span class="source-title">${escapeHtml(s.title)}</span>`}
                                ${s.p !== undefined ? `<span class="source-confidence" style="color: #666; font-size: 0.9em;"> (Conf = ${s.p.toFixed(2)})</span>` : ''}
                                ${s.snippet ? `
                                    <small class="source-snippet ${isLongSnippet ? 'expandable collapsed' : ''}" id="${snippetId}" ${isLongSnippet ? `onclick="InteractiveTable.toggleSnippet('${snippetId}')" title="Click to show more"` : ''}>
                                        ${isLongSnippet ? '<span class="snippet-arrow">▶</span>' : ''}
                                        <span class="snippet-text">"${escapeHtml(isLongSnippet ? shortSnippet : s.snippet)}"</span>
                                        ${isLongSnippet ? `<span class="snippet-full" style="display: none;">"${escapeHtml(s.snippet)}"</span>` : ''}
                                    </small>
                                ` : ''}
                            </li>
                        `}).join('')}
                    </ul>
                </div>
                ` : ''}
            </div>
        `;

        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.className = 'cell-detail-overlay' + (noAnimate ? ' no-animate' : '');
        overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
        overlay.innerHTML = modalContent;
        document.body.appendChild(overlay);

        // Add keyboard handler
        document.addEventListener('keydown', handleModalKeydown);
    }

    /**
     * Close cell detail modal
     */
    function closeModal(animate = false) {
        const overlay = document.querySelector('.cell-detail-overlay');
        if (overlay) {
            if (animate) {
                overlay.classList.add('modal-closing');
                setTimeout(() => overlay.remove(), 100);
            } else {
                overlay.remove();
            }
        }
        currentModalCell = null;
        document.removeEventListener('keydown', handleModalKeydown);
    }

    /**
     * Handle keyboard events in modal
     */
    function handleModalKeydown(e) {
        if (e.key === 'Escape') {
            closeModal();
        } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            navigateModalCell(-1, 'horizontal');
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            navigateModalCell(1, 'horizontal');
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            navigateModalCell(-1, 'vertical');
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            navigateModalCell(1, 'vertical');
        } else if (e.key === ' ') {
            // Space scrolls the modal down
            e.preventDefault();
            const modal = document.querySelector('.cell-detail-modal');
            if (modal) {
                modal.scrollBy({ top: 150, behavior: 'smooth' });
            }
        }
    }

    /**
     * Get all interactive cells in reading order
     */
    function getAllInteractiveCells() {
        return Array.from(document.querySelectorAll('.interactive-table .table-cell'));
    }

    /**
     * Navigate to prev/next cell in modal
     */
    function navigateModalCell(direction, mode = 'horizontal') {
        if (!currentModalCell) return;

        const cells = getAllInteractiveCells();
        const currentIndex = cells.indexOf(currentModalCell);
        if (currentIndex === -1) return;

        let targetCell = null;

        if (mode === 'horizontal') {
            const newIndex = currentIndex + direction;
            if (newIndex >= 0 && newIndex < cells.length) {
                targetCell = cells[newIndex];
            }
        } else if (mode === 'vertical') {
            const currentRow = currentModalCell.closest('tr');
            const currentColIndex = currentModalCell.dataset.colIndex;

            const allRows = Array.from(document.querySelectorAll('.interactive-table tbody tr'));
            const currentRowIndex = allRows.indexOf(currentRow);
            const targetRowIndex = currentRowIndex + direction;

            if (targetRowIndex >= 0 && targetRowIndex < allRows.length) {
                targetCell = allRows[targetRowIndex].querySelector(`.table-cell[data-col-index="${currentColIndex}"]`);
            }
        }

        if (targetCell) {
            // Clear any pending settle timeout
            if (navSettleTimeout) {
                clearTimeout(navSettleTimeout);
            }

            const overlay = document.querySelector('.cell-detail-overlay');

            // Scroll only within the table container (not the whole page)
            const container = targetCell.closest('.interactive-table-container');
            if (container) {
                const cellRect = targetCell.getBoundingClientRect();
                const containerRect = container.getBoundingClientRect();

                let scrollLeft = container.scrollLeft;
                let scrollTop = container.scrollTop;

                // Check if cell is outside visible area horizontally
                if (cellRect.left < containerRect.left || cellRect.right > containerRect.right) {
                    scrollLeft = targetCell.offsetLeft - container.offsetWidth / 2 + targetCell.offsetWidth / 2;
                }
                // Check if cell is outside visible area vertically (non-transposed mode)
                if (cellRect.top < containerRect.top || cellRect.bottom > containerRect.bottom) {
                    scrollTop = targetCell.offsetTop - container.offsetHeight / 2 + targetCell.offsetHeight / 2;
                }
                container.scrollTo({ left: scrollLeft, top: scrollTop, behavior: 'smooth' });
            }

            // Clear previous highlights
            const prevHighlighted = document.querySelectorAll('.interactive-table .column-highlight');
            prevHighlighted.forEach(c => c.classList.remove('column-highlight'));
            const prevRows = document.querySelectorAll('.interactive-table .row-highlight');
            prevRows.forEach(r => r.classList.remove('row-highlight'));
            const prevCells = document.querySelectorAll('.interactive-table .cell-hover-active');
            prevCells.forEach(c => c.classList.remove('cell-hover-active'));

            // Trigger hover state on target cell (highlight row/column)
            targetCell.classList.add('cell-hover-active');
            const colIndex = targetCell.dataset.colIndex;
            if (colIndex) {
                const colCells = document.querySelectorAll(`.interactive-table [data-col-index="${colIndex}"]`);
                colCells.forEach(c => c.classList.add('column-highlight'));
            }
            // Highlight the row (sticky column)
            const row = targetCell.closest('tr');
            if (row) {
                row.classList.add('row-highlight');
            }

            // Fade modal to transparent to reveal the highlighted cell
            if (overlay) {
                overlay.classList.add('modal-nav-fade');
            }

            // Update current cell reference
            currentModalCell = targetCell;

            // Settle after 1s of no movement - show new modal
            navSettleTimeout = setTimeout(() => {
                // Clear hover state
                targetCell.classList.remove('cell-hover-active');
                const highlighted = document.querySelectorAll('.interactive-table .column-highlight');
                highlighted.forEach(c => c.classList.remove('column-highlight'));
                const highlightedRows = document.querySelectorAll('.interactive-table .row-highlight');
                highlightedRows.forEach(r => r.classList.remove('row-highlight'));

                if (overlay) overlay.remove();
                showCellModal(targetCell, true, true);
                navSettleTimeout = null;
            }, 1000);
        }
    }

    /**
     * Navigate to previous cell
     */
    function navigatePrev() {
        navigateModalCell(-1);
    }

    /**
     * Navigate to next cell
     */
    function navigateNext() {
        navigateModalCell(1);
    }

    /* ========================================
     * Event Handlers - General Notes
     * ======================================== */

    /**
     * Toggle general notes box expansion
     */
    function toggleGeneralNotes(id) {
        const box = document.getElementById(id);
        if (box) {
            box.classList.toggle('collapsed');
            const isCollapsed = box.classList.contains('collapsed');
            const toggle = box.querySelector('.general-notes-toggle');
            if (toggle) {
                toggle.textContent = isCollapsed ? '▼' : '▲';
            }
            const hint = box.querySelector('.general-notes-expand-hint');
            if (hint) {
                hint.textContent = isCollapsed ? '(click to expand)' : '(click to collapse)';
            }
        }
    }

    /**
     * Toggle source snippet expansion
     */
    function toggleSnippet(snippetId) {
        const snippet = document.getElementById(snippetId);
        if (!snippet) return;

        const isCollapsed = snippet.classList.contains('collapsed');
        snippet.classList.toggle('collapsed');

        const shortText = snippet.querySelector('.snippet-text');
        const fullText = snippet.querySelector('.snippet-full');
        const arrow = snippet.querySelector('.snippet-arrow');

        if (isCollapsed) {
            // Expanding
            if (shortText) shortText.style.display = 'none';
            if (fullText) fullText.style.display = 'inline';
            if (arrow) arrow.textContent = '▼';
            snippet.title = 'Click to show less';
        } else {
            // Collapsing
            if (shortText) shortText.style.display = 'inline';
            if (fullText) fullText.style.display = 'none';
            if (arrow) arrow.textContent = '▶';
            snippet.title = 'Click to show more';
        }
    }

    /* ========================================
     * Initialization
     * ======================================== */

    /**
     * Initialize event handlers (call after rendering)
     */
    function init() {
        // Touch device detection
        if (!isTouchDevice) {
            document.addEventListener('touchstart', function onFirstTouch() {
                isTouchDevice = true;
                document.body.classList.add('touch-device');
                document.removeEventListener('touchstart', onFirstTouch);
            }, { passive: true });
        }
    }

    /* ========================================
     * Public API
     * ======================================== */
    return {
        render: render,
        fromSampleRows: fromSampleRows,
        init: init,
        // Tooltip handlers (called from inline event handlers)
        showTooltip: showTooltip,
        hideTooltip: hideTooltip,
        highlightColumn: highlightColumn,
        clearColumnHighlight: clearColumnHighlight,
        // Modal handlers
        showCellModal: showCellModal,
        closeModal: closeModal,
        navigatePrev: navigatePrev,
        navigateNext: navigateNext,
        // Notes handler
        toggleGeneralNotes: toggleGeneralNotes,
        toggleSnippet: toggleSnippet,
        // Utility
        escapeHtml: escapeHtml,
        // Transpose toggle
        transposeInCard: transposeInCard
    };
})();

// Expose to global scope for inline event handlers
window.InteractiveTable = InteractiveTable;

// Export for use in other modules (if using module system)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = InteractiveTable;
}
