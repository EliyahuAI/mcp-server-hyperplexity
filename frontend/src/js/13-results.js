/* ========================================
 * 13-results.js - Results Display
 *
 * Handles preview results display, cost estimates,
 * and action buttons for processing.
 *
 * Dependencies: 00-config.js, 05-chat.js, 16-interactive-table.js
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

        // Check if revert button should be shown (only if this session has 2+ versions)
        const sessionVersionCount = previewData.session_version_count || 0;
        const showRevertButton = sessionVersionCount >= 2;

        const revertButtonHtml = showRevertButton ?
            `<button type="button" class="std-button quaternary" data-action="revert-config">
                    ↩️ Revert to Previous
                </button>` : '';

        // Fixed colors for preview card buttons
        const downloadColor = 'tertiary';  // orange
        const refineColor = 'secondary';   // purple

        // Hide refine button for reference check (static config cannot be refined)
        const refineButtonHtml = !globalState.isReferenceCheck ?
            `<button type="button" class="std-button ${refineColor}" data-action="refine-config">
                🔧 Refine Configuration
            </button>` : '';

        const actionsHtml = `
            <div style="display: flex; gap: 10px; margin-bottom: 10px; justify-content: center; flex-wrap: wrap;">
                <button type="button" class="std-button ${downloadColor}" data-action="download-preview">
                    📥 Download Excel
                </button>
                <button type="button" class="std-button quaternary" data-action="download-json">
                    📋 Download JSON (for AI)
                </button>
                ${refineButtonHtml}
            </div>
            ${revertButtonHtml ? `<div style="display: flex; gap: 10px; margin-bottom: 20px; justify-content: center;">${revertButtonHtml}</div>` : ''}
        `;

        // Build complete HTML upfront to avoid innerHTML += race condition with async fetch
        const tableContainerId = `${cardId}-table-container`;
        previewContent.innerHTML = headerHtml + `
            <div id="${tableContainerId}">
                <p style="color: #999; font-style: italic; text-align: center; padding: 1rem;">Loading interactive table...</p>
            </div>
        ` + actionsHtml;

        // Store the download URL for the button
        previewContent.dataset.fullPreviewUrl = fullPreviewUrl;

        // Fetch table metadata via API (async, non-blocking)
        // This avoids WebSocket payload size limits (same pattern as full validation)
        fetchAndRenderPreviewTable(tableContainerId, globalState.sessionId, previewData.markdown_table);
    }

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
        const jsonBtn = card.querySelector('[data-action="download-json"]');
        const refineBtn = card.querySelector('[data-action="refine-config"]');
        const revertBtn = card.querySelector('[data-action="revert-config"]');

        if (downloadBtn) {
            downloadBtn.addEventListener('click', async () => {
                markDownloadStart();
                await downloadPreviewResults(previewData);
            });
        }

        if (jsonBtn) {
            jsonBtn.addEventListener('click', () => {
                // Use fetched metadata from API (stored in globalState)
                if (globalState.previewTableMetadata) {
                    downloadJsonMetadata(globalState.previewTableMetadata, jsonBtn);
                } else {
                    showMessage(`${cardId}-messages`, 'JSON metadata still loading. Please wait a moment and try again.', 'info');
                }
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
 * Preview Table Fetching
 * Fetches table metadata via API (same pattern as full validation)
 * This avoids WebSocket payload size limits
 * ======================================== */

async function fetchAndRenderPreviewTable(containerId, sessionId, fallbackMarkdown) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn('[PREVIEW] Table container not found:', containerId);
        return;
    }

    try {
        console.log('[PREVIEW] Fetching table metadata via API for session:', sessionId);
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'getViewerData',
                email: globalState.email,
                session_id: sessionId,
                is_preview: true  // Request preview data (3 rows)
            })
        });

        const data = await response.json();

        if (data.success && data.table_metadata) {
            // Store for JSON download
            globalState.previewTableMetadata = data.table_metadata;

            // Render interactive table
            if (typeof InteractiveTable !== 'undefined') {
                container.innerHTML = InteractiveTable.render(data.table_metadata, {
                    showGeneralNotes: true,
                    showLegend: true
                });
                InteractiveTable.init();
                console.log('[PREVIEW] Interactive table rendered successfully');
            } else {
                console.warn('[PREVIEW] InteractiveTable not available, using markdown fallback');
                container.innerHTML = renderMarkdown(fallbackMarkdown || '');
            }
        } else {
            console.warn('[PREVIEW] API returned no table_metadata, using markdown fallback:', data.error || 'unknown');
            container.innerHTML = renderMarkdown(fallbackMarkdown || '');
        }
    } catch (error) {
        console.error('[PREVIEW] Failed to fetch table metadata:', error);
        // Fallback to markdown
        container.innerHTML = renderMarkdown(fallbackMarkdown || '');
    }
}

/* ========================================
 * Interactive Table Preview Functions
 * NOTE: Table rendering is now handled by 16-interactive-table.js (InteractiveTable module)
 * The functions below provide backwards compatibility for legacy window.* calls
 * ======================================== */

// Backwards compatibility - redirect to InteractiveTable module
window.toggleGeneralNotes = function(id) {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.toggleGeneralNotes(id);
    }
};

window.showCellDetailModal = function(cellElement) {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.showCellModal(cellElement);
    }
};

window.closeCellDetailModal = function() {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.closeModal();
    }
};

window.navigateToPrevCell = function() {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.navigatePrev();
    }
};

window.navigateToNextCell = function() {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.navigateNext();
    }
};

window.showCustomTooltip = function(event, cell) {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.showTooltip(event, cell);
    }
};

window.hideCustomTooltip = function() {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.hideTooltip();
    }
};

window.highlightColumn = function(colIndex) {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.highlightColumn(colIndex);
    }
};

window.clearColumnHighlight = function() {
    if (typeof InteractiveTable !== 'undefined') {
        InteractiveTable.clearColumnHighlight();
    }
};
