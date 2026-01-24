/* ========================================
 * 13-results.js - Results Display
 *
 * Handles preview results display, cost estimates,
 * and action buttons for processing.
 *
 * Dependencies: 00-config.js, 05-chat.js
 * ======================================== */

function showPreviewResults(cardId, previewData) {
    // Save preview data globally for restoration
    window.lastPreviewData = previewData;

    // Mark preview as completed
    ensureProcessingState();
    globalState.processingState.previewCompleted = true;

    // Hide progress, show results
    const resultsEl = document.getElementById(`${cardId}-results`);
    if (!resultsEl) {
        console.error(`Results element ${cardId}-results not found`);
        return;
    }
    resultsEl.style.display = 'block';

    // Render markdown table with blue info header
    const previewContent = document.getElementById(`${cardId}-preview-content`);
    if (previewContent && previewData.markdown_table) {
        // Generate download URL for full preview
        let fullPreviewUrl = '#';
        if (previewData.enhanced_download_url) {
            fullPreviewUrl = previewData.enhanced_download_url;
        } else if (previewData.full_preview_url) {
            fullPreviewUrl = previewData.full_preview_url;
        } else if (globalState.sessionId) {
            // Generate preview download URL based on session
            fullPreviewUrl = `${API_BASE}/download/${globalState.sessionId}/preview_results.xlsx`;
        }

        const headerHtml = `
            <div class="message message-info">
                <span class="message-icon">ℹ️</span>
                <span>This preview shows the first 3 rows of Updated values (transposed). An Excel version can be downloaded at the button below.</span>
            </div>
        `;

        // Use interactive table if metadata available, otherwise fallback to markdown
        console.log('[TABLE_PREVIEW] table_metadata:', previewData.table_metadata ? 'present' : 'missing', previewData.table_metadata);
        if (previewData.table_metadata) {
            const interactiveTable = renderInteractiveTable(previewData.table_metadata);
            previewContent.innerHTML = headerHtml + (interactiveTable || renderMarkdown(previewData.markdown_table));
        } else {
            previewContent.innerHTML = headerHtml + renderMarkdown(previewData.markdown_table);
        }

        // Store the download URL for the button
        previewContent.dataset.fullPreviewUrl = fullPreviewUrl;
    }

    // Add buttons above estimates
    // Check if revert button should be shown (only if this session has 2+ versions)
    // Use session_version_count if available (accurate), otherwise fall back to config_version
    const sessionVersionCount = previewData.session_version_count || 0;
    const currentVersion = previewData.config_version || globalState.currentConfig?.config_version || 1;
    const showRevertButton = sessionVersionCount >= 2;

    const revertButtonHtml = showRevertButton ?
        `<button type="button" class="std-button quaternary" data-action="revert-config">
                ↩️ Revert to Previous
            </button>` : '';

    // Fixed colors for preview card buttons
    // Download = orange, Refine = purple, Revert = cyan (when shown), Process = green
    const downloadColor = 'tertiary';  // orange
    const refineColor = 'secondary';   // purple

    // Hide refine button for reference check (static config cannot be refined)
    const refineButtonHtml = !globalState.isReferenceCheck ?
        `<button type="button" class="std-button ${refineColor}" data-action="refine-config">
            🔧 Refine Configuration
        </button>` : '';

    const actionsHtml = `
        <div style="display: flex; gap: 10px; margin-bottom: 20px; justify-content: center;">
            <button type="button" class="std-button ${downloadColor}" data-action="download-preview">
                📥 Download Excel Preview
            </button>
            ${refineButtonHtml}
            ${revertButtonHtml}
        </div>
    `;
    previewContent.innerHTML += actionsHtml;

    // Calculate cost values ONCE before display and button logic to ensure consistency
    const estimatedCost = previewData.cost_estimates ? (previewData.cost_estimates.quoted_validation_cost || previewData.cost_estimates.quoted_full_cost) : 0;
    const discount = previewData.cost_estimates?.discount || previewData.discount || 0;
    const effectiveCost = previewData.cost_estimates?.effective_cost !== undefined
        ? previewData.cost_estimates.effective_cost
        : Math.max(0, estimatedCost - discount);
    const accountInfo = previewData.account_info;
    const currentBalance = accountInfo?.current_balance || 0;
    // TRUST THE BACKEND - use its balance calculations, don't recalculate
    const sufficientBalance = accountInfo?.sufficient_balance ?? true;
    const creditsNeeded = accountInfo?.credits_needed || 0;

    // Store in global state for later use
    globalState.estimatedCost = estimatedCost;
    globalState.discount = discount;
    globalState.effectiveCost = effectiveCost;
    globalState.accountInfo = accountInfo;

    // Show cost estimates
    if (previewData.cost_estimates && previewData.validation_metrics) {
        const costEl = document.getElementById(`${cardId}-cost-estimate`);
        const estimatesEl = document.getElementById(`${cardId}-estimates`);

        if (costEl && estimatesEl) {
            costEl.style.display = 'block';

            const metrics = previewData.validation_metrics;
            const totalRows = previewData.total_rows || 0;
            const estimatedTime = previewData.cost_estimates.estimated_validation_time || 0;

            let estimatesHtml = '';

            if (totalRows > 0) {
                estimatesHtml += `<div class="cost-item"><span class="cost-label">Total Rows</span><span class="cost-value">${totalRows.toLocaleString()}</span></div>`;
            }

            if (metrics.validated_columns_count) {
                estimatesHtml += `<div class="cost-item"><span class="cost-label">Columns to Validate</span><span class="cost-value">${metrics.validated_columns_count}</span></div>`;
            }

            // Show total AI calls (validation + QC calls)
            // Clone counts as 1 call even if it makes multiple internal calls
            const totalSearchGroups = metrics.search_groups_count || 0;
            const qcCallsPerRow = metrics.qc_calls_per_row || 0;

            // DEBUG: Log the values being used
            console.log('[AI_CALLS_CALC] validation_metrics:', metrics);
            console.log('[AI_CALLS_CALC] totalRows:', totalRows);
            console.log('[AI_CALLS_CALC] search_groups_count:', totalSearchGroups);
            console.log('[AI_CALLS_CALC] qc_calls_per_row:', qcCallsPerRow);

            if (totalSearchGroups > 0 || qcCallsPerRow > 0) {
                // Total AI calls = (validation calls per row + QC calls per row) × total rows
                const callsPerRow = totalSearchGroups + qcCallsPerRow;
                const totalAICalls = totalRows * callsPerRow;
                console.log('[AI_CALLS_CALC] callsPerRow:', callsPerRow, '(groups:', totalSearchGroups, '+ QC:', qcCallsPerRow, ')');
                console.log('[AI_CALLS_CALC] totalAICalls:', totalAICalls, '(', totalRows, '×', callsPerRow, ')');
                estimatesHtml += `<div class="cost-item"><span class="cost-label">Total AI Calls</span><span class="cost-value">${totalAICalls.toLocaleString()}</span></div>`;
            }

            estimatesHtml += `<div class="cost-item"><span class="cost-label">Est. Time</span><span class="cost-value">${Math.ceil(estimatedTime / 60)} min</span></div>`;

            // Display cost with discount if applicable (using pre-calculated values)
            if (discount > 0) {
                estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost → Discounted</span><span class="cost-value"><span style="text-decoration: line-through; color: #999;">$${estimatedCost.toFixed(2)}</span> → $${effectiveCost.toFixed(2)}</span></div>`;
            } else {
                estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost</span><span class="cost-value">$${estimatedCost.toFixed(2)}</span></div>`;
            }

            // Domain multiplier is hidden from frontend display

            // Add account balance information if available (using pre-calculated values)
            if (accountInfo) {
                estimatesHtml += `<hr style="margin: 10px 0; border: none; border-top: 1px solid #eee;">`;
                estimatesHtml += `<div class="cost-item"><span class="cost-label">Your Balance</span><span class="cost-value">$${currentBalance.toFixed(2)}</span></div>`;

                if (!sufficientBalance && creditsNeeded > 0) {
                    estimatesHtml += `<div class="cost-item"><span class="cost-label" style="color: #f44336;">Credits Needed</span><span class="cost-value" style="color: #f44336;">$${creditsNeeded.toFixed(2)}</span></div>`;
                }
            }

            estimatesEl.innerHTML = estimatesHtml;

        }
    }

    const card = document.getElementById(cardId);

    // Values already calculated above and stored in outer scope, ready for use

    // Add event listeners for the buttons above estimates
    setTimeout(() => {
        const downloadBtn = card.querySelector('[data-action="download-preview"]');
        const refineBtn = card.querySelector('[data-action="refine-config"]');
        const revertBtn = card.querySelector('[data-action="revert-config"]');

        if (downloadBtn) {
            downloadBtn.addEventListener('click', async () => {
                markDownloadStart();
                await downloadPreviewResults(previewData);
            });
        }

        if (refineBtn) {
            refineBtn.addEventListener('click', debounceConfigAction('refine-config', async () => {
                // Don't use markButtonSelected as it expects different button structure
                refineBtn.disabled = true;
                refineBtn.textContent = '🔧 Refining...';
                globalState.activePreviewCard = null;
                await createRefinementCard();
            }));
        }

        // Only add revert button listener if the button exists (version > 1)
        if (revertBtn) {
            revertBtn.addEventListener('click', debounceConfigAction('revert-config', async () => {
                revertBtn.disabled = true;
                revertBtn.textContent = '↩️ Reverting...';
                globalState.activePreviewCard = null;
                await createConfigCardWithId('last');
            }));
        }
    }, 100);

    // Show single Process Table button at bottom
    // Calculate discount and effectiveCost from preview data (recalculate to ensure we have fresh values)
    const buttonDiscount = previewData.cost_estimates?.discount || previewData.discount || 0;
    const buttonEffectiveCost = previewData.cost_estimates?.effective_cost !== undefined
        ? previewData.cost_estimates.effective_cost
        : Math.max(0, estimatedCost - buttonDiscount);

    let buttonCostText = '';
    if (estimatedCost) {
        if (buttonDiscount > 0) {
            // Show strikethrough original cost → discounted price (same format as cost display)
            buttonCostText = ` (<span style="text-decoration: line-through;">$${estimatedCost.toFixed(2)}</span> → $${buttonEffectiveCost.toFixed(2)})`;
        } else {
            buttonCostText = ` ($${estimatedCost.toFixed(2)})`;
        }
    }

    createButtonRow(`${cardId}-buttons`, [
        {
            text: sufficientBalance
                ? `Process Table${buttonCostText}`
                : `Add Credits ($${Math.ceil(creditsNeeded).toFixed(2)})`,
            icon: sufficientBalance ? '✨' : '💳',
            variant: sufficientBalance ? 'primary' : 'secondary',
            width: 'full',
            callback: async (e) => {
                const button = e.target.closest('button');

                if (sufficientBalance) {
                    // User has sufficient balance - proceed with processing
                    globalState.hasInsufficientBalance = false;
                    markButtonSelected(button, '✨ Processing...');
                    globalState.activePreviewCard = null;
                    createProcessingCard();
                } else {
                    // Insufficient balance - open add credits page
                    globalState.hasInsufficientBalance = true;
                    // Mark that user attempted processing from preview
                    globalState.userAttemptedProcessing = true;
                    globalState.pendingProcessingTrigger = () => {
                        // console.trace('[AUTO-TRIGGER] Stack trace:');
                        globalState.activePreviewCard = null;

                        // Find and click the Process Table button to trigger normal processing
                        const buttons = document.querySelectorAll('button');
                        for (const button of buttons) {
                            const buttonText = button.querySelector('.button-text, span');
                            if (buttonText && buttonText.textContent.includes('Process Table')) {
                                button.click();
                                break;
                            }
                        }
                    };
                    markButtonSelected(button, '💳 Opening store...');
                    // Use effective cost-based creditsNeeded (already calculated above using effectiveCost)
                    const recommendedAmount = Math.ceil(creditsNeeded); // Round up to nearest dollar
                    openAddCreditsPage(recommendedAmount, `${cardId}-messages`);

                    // Reset button after a delay
                    setTimeout(() => {
                        markButtonUnselected(button);
                    }, 2000);
                }
            }
        }
    ]);

    // Show instruction message for Add Credits button
    if (!sufficientBalance) {
        showMessage(`${cardId}-messages`, `💳 Click button to add credits. After purchase, return to this tab for auto-processing.`, 'info', false, 'add-credits-instruction');
    }
}

/* ========================================
 * Interactive Table Preview Functions
 * ======================================== */

/**
 * Render an interactive table with frozen first column and tooltips
 */
function renderInteractiveTable(tableMetadata) {
    // Bug fix #1: Check both rows AND columns exist and are non-empty
    if (!tableMetadata || !tableMetadata.rows || tableMetadata.rows.length === 0 ||
        !tableMetadata.columns || tableMetadata.columns.length === 0) {
        return null;
    }

    const { columns, rows, general_notes } = tableMetadata;

    let html = '';

    // General notes info box (collapsible if long)
    if (general_notes && general_notes.trim()) {
        const isLong = general_notes.length > 200;
        const uniqueId = 'general-notes-' + Date.now();
        html += `<div class="general-notes-box${isLong ? ' collapsible collapsed' : ''}" ${isLong ? `onclick="toggleGeneralNotes('${uniqueId}')"` : ''} id="${uniqueId}">
            <div class="general-notes-header">
                <span class="general-notes-icon">📋</span>
                <span class="general-notes-title">Configuration Notes</span>
                ${isLong ? '<span class="general-notes-toggle">▼</span>' : ''}
            </div>
            <div class="general-notes-content">${escapeHtmlForTable(general_notes)}</div>
        </div>`;
    }

    // Color legend/key
    html += `<div class="table-legend">
        <span class="legend-title">Confidence:</span>
        <span class="legend-item"><span class="legend-color confidence-high"></span> High</span>
        <span class="legend-item"><span class="legend-color confidence-medium"></span> Medium</span>
        <span class="legend-item"><span class="legend-color confidence-low"></span> Low</span>
        <span class="legend-item"><span class="legend-color confidence-id"></span> ID</span>
    </div>`;

    html += '<div class="interactive-table-container">';
    html += '<table class="interactive-table">';

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
        // Bug fix #2: Both ID and IGNORED columns should show as ID style
        const importance = col.importance ? col.importance.toUpperCase() : '';
        const isIdColumn = importance === 'ID' || importance === 'IGNORED';

        // Build column header tooltip from description and notes
        const colTooltip = buildColumnTooltip(col.description, col.notes);
        const hasTooltip = colTooltip && colTooltip.length > 0;

        html += '<tr>';
        html += `<td class="sticky-column ${isIdColumn ? 'id-column' : ''}${hasTooltip ? ' has-column-info' : ''}" data-col-index="0"`;
        if (hasTooltip) {
            html += ` data-tooltip-html="${colTooltip.replace(/"/g, '&quot;')}"`;
            html += ` onmouseenter="showCustomTooltip(event, this)"`;
            html += ` onmouseleave="hideCustomTooltip()"`;
        }
        html += '>';
        html += `<strong>${escapeHtmlForTable(col.name)}</strong>`;
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
            const rowIdValues = idColumns.map(idCol => row.cells[idCol.name]?.display_value || '').filter(v => v).join(', ');
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

            // Bug fix #4: Properly escape JSON for HTML attribute (handle quotes, newlines, special chars)
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
                onclick="showCellDetailModal(this)"
                onmouseenter="showCustomTooltip(event, this); highlightColumn(${colIdx + 1})"
                onmouseleave="hideCustomTooltip(); clearColumnHighlight()"
            >`;
            html += `<span class="cell-value">${escapeHtmlForTable(displayValue)}</span>`;
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
        const truncated = fullValue.substring(0, 200) + (fullValue.length > 200 ? '...' : '');
        parts.push(`<b>Full:</b> ${escapeHtmlForTable(truncated)}`);
    }

    if (comment.validator_explanation) {
        const explanation = comment.validator_explanation.length > 150
            ? comment.validator_explanation.substring(0, 150) + '...'
            : comment.validator_explanation;
        parts.push(`<b>Reason:</b> ${escapeHtmlForTable(explanation)}`);
    }

    if (comment.key_citation) {
        const citation = comment.key_citation.length > 100
            ? comment.key_citation.substring(0, 100) + '...'
            : comment.key_citation;
        parts.push(`<b>Key Citation:</b> ${escapeHtmlForTable(citation)}`);
    }

    if (parts.length > 0) {
        parts.push('<span class="tooltip-hint">Click for more</span>');
    }
    return parts.join('<br>');
}

function buildColumnTooltip(description, notes) {
    let parts = [];

    if (description && description.trim()) {
        parts.push(`<b>Description:</b> ${escapeHtmlForTable(description)}`);
    }

    if (notes && notes.trim()) {
        parts.push(`<b>Notes:</b> ${escapeHtmlForTable(notes)}`);
    }

    return parts.join('<br>');
}

// Toggle general notes box expansion
window.toggleGeneralNotes = function(id) {
    const box = document.getElementById(id);
    if (box) {
        box.classList.toggle('collapsed');
        const toggle = box.querySelector('.general-notes-toggle');
        if (toggle) {
            toggle.textContent = box.classList.contains('collapsed') ? '▼' : '▲';
        }
    }
};

// Expose to global scope for onclick handlers
window.showCellDetailModal = function(cellElement) {
    // Track current cell for navigation
    currentModalCell = cellElement;

    // Determine navigation state
    const cells = getAllInteractiveCells();
    const currentIndex = cells.indexOf(cellElement);
    const hasPrev = currentIndex > 0;
    const hasNext = currentIndex < cells.length - 1;

    // Bug fix #4 continued: Decode HTML entities before parsing JSON
    let cellDataStr = cellElement.dataset.cellData || '{}';
    cellDataStr = cellDataStr
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&');
    const cellData = JSON.parse(cellDataStr);
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

    // Format confidence text (e.g., "HIGH" -> "HIGH CONFIDENCE")
    const formatConfidence = (conf) => {
        if (!conf) return '';
        if (conf === 'ID') return 'ID';
        return conf + ' CONFIDENCE';
    };

    // Format value with newlines preserved
    const formatValue = (val) => {
        if (!val) return '-';
        return escapeHtmlForTable(val).replace(/\n/g, '<br>');
    };

    // Determine if value was updated
    const currentValue = cellData.full_value || cellData.display_value || '-';
    const originalValue = comment.original_value;
    const originalConfidence = comment.original_confidence ? comment.original_confidence.toUpperCase() : '';

    // Debug logging
    console.log('[MODAL] currentValue:', JSON.stringify(currentValue));
    console.log('[MODAL] originalValue:', JSON.stringify(originalValue));

    // Check if updated - compare normalized values
    const normalizeValue = (v) => v === undefined || v === null ? '' : String(v).replace(/\s+/g, ' ').trim();
    const isUpdated = originalValue !== undefined && originalValue !== '' &&
                      normalizeValue(originalValue) !== normalizeValue(currentValue);
    console.log('[MODAL] isUpdated:', isUpdated);

    const columnName = cellData._columnName || 'Unknown';
    const rowId = cellData._rowId || 'Unknown';

    let modalContent = `
        <div class="cell-detail-modal">
            <div class="cell-detail-header">
                <div class="cell-detail-nav">
                    <button class="modal-nav-btn" onclick="navigateToPrevCell()" ${!hasPrev ? 'disabled' : ''} title="Previous cell (←)">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
                    </button>
                </div>
                <div class="cell-detail-title">
                    <h3>${escapeHtmlForTable(columnName)}</h3>
                    <span class="cell-detail-row-id">${escapeHtmlForTable(rowId)}</span>
                </div>
                <div class="cell-detail-actions">
                    <button class="modal-nav-btn" onclick="navigateToNextCell()" ${!hasNext ? 'disabled' : ''} title="Next cell (→)">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
                    </button>
                    <button class="modal-close" onclick="closeCellDetailModal()">&times;</button>
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
                <p class="detail-value">${escapeHtmlForTable(comment.validator_explanation)}</p>
            </div>
            ` : ''}

            ${comment.qc_reasoning ? `
            <div class="detail-section">
                <label>✅ QC Reasoning</label>
                <p class="detail-value">${escapeHtmlForTable(comment.qc_reasoning)}</p>
            </div>
            ` : ''}

            ${comment.key_citation ? `
            <div class="detail-section">
                <label>🔗 Key Citation</label>
                <p class="detail-value">${escapeHtmlForTable(comment.key_citation)}</p>
            </div>
            ` : ''}

            ${comment.sources && comment.sources.length > 0 ? `
            <div class="detail-section">
                <label>📚 Sources</label>
                <ul class="sources-list">
                    ${comment.sources.map(s => `
                        <li>
                            <span class="source-id">[${s.id}]</span>
                            ${s.url ? `<a href="${escapeHtmlForTable(s.url)}" target="_blank">${escapeHtmlForTable(s.title)}</a>` : escapeHtmlForTable(s.title)}
                            ${s.snippet ? `<br><small class="source-snippet">"${escapeHtmlForTable(s.snippet.substring(0, 150))}${s.snippet.length > 150 ? '...' : ''}"</small>` : ''}
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

    // Add keyboard handler for escape and arrow navigation
    document.addEventListener('keydown', handleModalKeydown);
}

window.closeCellDetailModal = function() {
    const overlay = document.querySelector('.cell-detail-overlay');
    if (overlay) overlay.remove();
    currentModalCell = null;
    document.removeEventListener('keydown', handleModalKeydown);
}

function handleModalKeydown(e) {
    if (e.key === 'Escape') {
        closeCellDetailModal();
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

// Get all interactive cells in reading order
function getAllInteractiveCells() {
    return Array.from(document.querySelectorAll('.interactive-table .table-cell'));
}

// Navigate to prev/next cell in modal
// direction: -1 (prev) or 1 (next)
// mode: 'horizontal' (left/right in reading order) or 'vertical' (up/down same column)
function navigateModalCell(direction, mode = 'horizontal') {
    if (!currentModalCell) return;

    const cells = getAllInteractiveCells();
    const currentIndex = cells.indexOf(currentModalCell);
    if (currentIndex === -1) return;

    let targetCell = null;

    if (mode === 'horizontal') {
        // Left/Right: move in reading order
        const newIndex = currentIndex + direction;
        if (newIndex >= 0 && newIndex < cells.length) {
            targetCell = cells[newIndex];
        }
    } else if (mode === 'vertical') {
        // Up/Down: move to same column in prev/next row
        const currentRow = currentModalCell.closest('tr');
        const currentColIndex = currentModalCell.dataset.colIndex;

        // Find the target row
        const allRows = Array.from(document.querySelectorAll('.interactive-table tbody tr'));
        const currentRowIndex = allRows.indexOf(currentRow);
        const targetRowIndex = currentRowIndex + direction;

        if (targetRowIndex >= 0 && targetRowIndex < allRows.length) {
            // Find the cell with the same column index in the target row
            targetCell = allRows[targetRowIndex].querySelector(`.table-cell[data-col-index="${currentColIndex}"]`);
        }
    }

    if (targetCell) {
        closeCellDetailModal();
        showCellDetailModal(targetCell);
    }
}

window.navigateToPrevCell = function() {
    navigateModalCell(-1);
};

window.navigateToNextCell = function() {
    navigateModalCell(1);
};

function escapeHtmlForTable(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

/* Custom Tooltip System */
let tooltipElement = null;
let tooltipTimeout = null;
let hoverDelayTimeout = null;
let currentHoverCell = null;

/* Modal Navigation State */
let currentModalCell = null;

/* Touch Device Detection */
let isTouchDevice = false;

// Detect touch device on first touch
document.addEventListener('touchstart', function onFirstTouch() {
    isTouchDevice = true;
    document.body.classList.add('touch-device');
    document.removeEventListener('touchstart', onFirstTouch);
}, { passive: true });

window.showCustomTooltip = function(event, cell) {
    // Skip tooltip system entirely on touch devices - tap goes straight to modal
    if (isTouchDevice) return;

    const html = cell.dataset.tooltipHtml;

    // Track current cell and store event coords
    currentHoverCell = cell;
    const coords = { x: event.clientX, y: event.clientY };

    // Immediately show cell saturation and column highlights (skip for sticky column headers)
    const colIndex = cell.dataset.colIndex;
    const isColumnHeader = colIndex === '0' || cell.classList.contains('sticky-column');

    if (!isColumnHeader) {
        cell.classList.add('cell-hover-active');
        if (colIndex) {
            const cells = document.querySelectorAll(`.interactive-table [data-col-index="${colIndex}"]`);
            cells.forEach(c => c.classList.add('column-highlight'));
        }
    }

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

    // Delay showing tooltip by 300ms (fast enough to feel responsive, slow enough to avoid spam)
    hoverDelayTimeout = setTimeout(() => {
        if (currentHoverCell !== cell) return; // Mouse moved away

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
};

window.hideCustomTooltip = function() {
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
};

// Column highlighting (triggered immediately in showCustomTooltip)
window.highlightColumn = function(colIndex) {
    // Kept for compatibility but handled in showCustomTooltip
};

window.clearColumnHighlight = function() {
    // Kept for compatibility but handled in hideCustomTooltip
};
