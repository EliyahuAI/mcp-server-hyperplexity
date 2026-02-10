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
                <span>Preview of first 3 rows (displayed as columns). Hover cells for quick info, click for full details. Use the buttons below to download, refine, or process the full table.</span>
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

async function fetchAndRenderPreviewTable(containerId, sessionId, fallbackMarkdown, retryCount = 0) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn('[PREVIEW] Table container not found:', containerId);
        return;
    }

    // Validate session ID format
    if (!sessionId || typeof sessionId !== 'string') {
        console.error('[PREVIEW] Invalid sessionId:', sessionId);
        container.innerHTML = `<p style="color: #999; font-style: italic; text-align: center; padding: 1rem;">Unable to load table: invalid session ID</p>`;
        return;
    }

    const maxRetries = 3;
    const retryDelay = 2000; // 2 seconds

    try {
        console.log(`[PREVIEW] Fetching table metadata via API for session: ${sessionId} (attempt ${retryCount + 1}/${maxRetries + 1})`);
        console.log('[PREVIEW] Session ID format check:', /^session_(demo_)?\d{8}_\d{6}_[a-f0-9]{8}$/.test(sessionId));

        const requestBody = {
            action: 'getViewerData',
            session_id: sessionId,
            is_preview: true  // Request preview data (3 rows)
        };

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        // SECURITY: Handle token revocation
        if (data.token_revoked) {
            console.error('[SECURITY] Token revoked by server - clearing session');

            // Clear session data
            localStorage.removeItem(SK_TOKEN);
            localStorage.removeItem(SK_EMAIL);
            sessionStorage.removeItem('validatedEmail');
            if (typeof globalState !== 'undefined') {
                globalState.sessionToken = null;
                globalState.email = null;
            }

            // Hide signed-in badge if function exists
            if (typeof hideSignedInBadge === 'function') {
                hideSignedInBadge();
            }

            // Show error message with reload button
            container.innerHTML = `
                <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 1.5rem; margin: 1rem 0;">
                    <div style="display: flex; align-items: start; gap: 0.75rem;">
                        <span style="font-size: 1.5rem;">⚠️</span>
                        <div>
                            <strong style="color: var(--text-primary);">Session Expired</strong>
                            <p style="color: var(--text-secondary); margin: 0.5rem 0 0 0;">
                                ${data.error || 'Your session has been revoked. Please log in again to view this data.'}
                            </p>
                            <button onclick="location.reload()" style="margin-top: 1rem; padding: 0.5rem 1rem; background: var(--primary-color); color: white; border: none; border-radius: 4px; cursor: pointer;">
                                Reload Page
                            </button>
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        // If metadata was too large to include inline, fetch it from S3
        if (data.success && data.metadata_too_large && data.json_download_url && !data.table_metadata) {
            console.log('[PREVIEW] Metadata too large, fetching from:', data.json_download_url);
            container.innerHTML = '<p style="color: #999; font-style: italic; text-align: center; padding: 1rem;">Loading large table data from S3...</p>';

            const metadataResponse = await fetch(data.json_download_url);
            if (!metadataResponse.ok) {
                throw new Error(`Failed to fetch metadata from S3: ${metadataResponse.status}`);
            }
            data.table_metadata = await metadataResponse.json();
            console.log('[PREVIEW] Successfully fetched large metadata from S3');
        }

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
            // Check if this is a 404 "session not found" (race condition) and retry
            if (response.status === 404 && data.session_not_found && retryCount < maxRetries) {
                console.log(`[PREVIEW] Session not found yet (race condition), retrying in ${retryDelay}ms...`);
                container.innerHTML = `<p style="color: #999; font-style: italic; text-align: center; padding: 1rem;">Loading table data (attempt ${retryCount + 2}/${maxRetries + 1})...</p>`;
                setTimeout(() => {
                    fetchAndRenderPreviewTable(containerId, sessionId, fallbackMarkdown, retryCount + 1);
                }, retryDelay);
                return;
            }

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
