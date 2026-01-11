/* ========================================
 * 12-validation.js - Full Validation Flow
 *
 * Handles full validation processing, batch operations,
 * and progress tracking.
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */

function ensureProcessingState() {
    if (!globalState.processingState || typeof globalState.processingState !== 'object') {
        console.warn('[GLOBALSTATE] Reinitializing null/invalid processingState');
        globalState.processingState = {
            previewCompleted: false,
            validationCompleted: false,
            validationStartTime: null,
            previewStartTime: null,
            lastEstimatedCost: null,
            lastBalanceCheck: null
        };
    }
}

// ============================================
// TESTING UTILITIES
function handleProcessingWebSocketMessage(data, cardId) {
    // WebSocket message received

    if (data.status === 'PROCESSING') {
        // Set this card as active for ticker display
        globalState.activeCardId = cardId;
        globalState.currentValidationState = 'full';

        // Clear confidence scores for fresh running average
        globalState.confidenceScores = [];
        globalState.currentConfidenceScore = null;

        let message = data.verbose_status || 'Processing...';

        // If we have batch information, format it nicely
        if (data.current_batch !== undefined && data.total_batches !== undefined) {
            message = `Processing batch ${data.current_batch} of ${data.total_batches}`;
            if (data.processed_rows !== undefined) {
                message += ` (${data.processed_rows} rows processed)`;
            }
        }

        // Update both text and progress if we have percent_complete
        if (data.percent_complete !== undefined) {
            updateThinkingProgress(cardId, data.percent_complete, message);
        } else {
            updateThinkingInCard(cardId, message);
        }
        // Progress routed to card level;

    } else if (data.status === 'COMPLETED') {
        // Hide ticker but KEEP messages for next validation
        globalState.currentValidationState = null;
        hideTicker(cardId);
        // DON'T clear messages - keep them for full validation after preview
        if (globalState.activeCardId === cardId) {
            globalState.activeCardId = null;
        }
        // Store completion data for download
        globalState.completionData = data;

        // Mark validation as completed
        ensureProcessingState();
        globalState.processingState.validationCompleted = true;
        globalState.workflowPhase = 'completed';
        // Reset guard flag - processing complete
        globalState.processingInProgress = false;
        
        // First update to 100% if we have a progress bar
        const indicator = document.getElementById(`${cardId}-thinking`);
        const hasProgress = indicator && indicator.classList.contains('with-progress');

        if (hasProgress) {
            updateThinkingProgress(cardId, 100, 'Validation complete!');
            setTimeout(() => {
                completeThinkingInCard(cardId, 'Validation complete!');
            }, 500);
        } else {
            completeThinkingInCard(cardId, 'Validation complete!');
        }
        // Progress routed to card level;

        globalState.processedRows = data.processed_rows || 0;
        globalState.totalRows = data.total_rows || 0;

        // Show success message after shrink animation completes (if progress bar present)
        // 500ms + 300ms (move to 100%) + 600ms (completion) + 1000ms (shrink) = 2400ms
        const showResultsDelay = hasProgress ? 2400 : 0;

        setTimeout(() => {
            const messagesContainer = document.getElementById(`${cardId}-messages`);
            if (messagesContainer) {
            // Show full results interface immediately, but with disabled download button
            const balanceText = globalState.accountBalance !== undefined ? 
                `• Remaining balance: $${globalState.accountBalance.toFixed(2)}` : 
                `• Balance updating...`;
            
            // Check if revert button should be shown (only if this session has 2+ versions)
            const sessionVersionCount = data.session_version_count || 0;
            const currentVersion = data.config_version || globalState.currentConfig?.config_version || 1;
            const showRevertButton = sessionVersionCount >= 2;

            // Calculate button colors based on reverse cycle (last button = green)
            // With revert (4 buttons): quaternary, tertiary, secondary, primary
            // Without revert (3 buttons): tertiary, secondary, primary
            const downloadColor = showRevertButton ? 'quaternary' : 'tertiary';
            const refineColor = showRevertButton ? 'tertiary' : 'secondary';
            const revertColor = 'secondary';
            const newValidationColor = 'primary';

            const revertButtonHtml = showRevertButton ?
                `<button class="std-button ${revertColor}" id="${cardId}-revert-btn" style="flex: 1;">
                        <span class="button-text">↩️ Revert to Previous</span>
                    </button>` : '';

            // Hide refine button for reference check (static config cannot be refined)
            const refineMessageHtml = !globalState.isReferenceCheck ?
                `<div style="margin-bottom: 8px;">
                    • If you want to change anything, refine the configuration and check out the preview
                </div>` : '';

            const refineButtonHtml = !globalState.isReferenceCheck ?
                `<button class="std-button ${refineColor}" id="${cardId}-refine-btn" style="flex: 1;">
                    <span class="button-text">🔧 Refine Configuration</span>
                </button>` : '';

            messagesContainer.innerHTML = `
                <div class="message message-success" style="margin-bottom: 1rem;">
                    <span class="message-icon">🎉</span>
                    <div style="line-height: 1.6;">
                        <div style="margin-bottom: 8px;">
                            • Your validation has been completed successfully and emailed to you
                        </div>
                        <div style="margin-bottom: 8px;">
                            • Notice the Updated and Original sheets, color coded by confidence: Green (High), Yellow (Medium), Red (Low), No Color (Null/Blank)
                        </div>
                        <div style="margin-bottom: 8px;">
                            • Enable editing to see key citations and sources in cell comments when hovering.
                        </div>
                        ${refineMessageHtml}
                        <div id="${cardId}-balance-info">
                            ${balanceText}
                        </div>
                    </div>
                </div>
                <div style="display: flex; gap: 10px; margin-top: 1rem;">
                    <button class="std-button ${downloadColor}" id="${cardId}-download-btn" style="flex: 1;" disabled>
                        <span class="button-text">📥 Preparing Download...</span>
                    </button>
                    ${refineButtonHtml}
                </div>
                <div style="display: flex; gap: 10px; margin-top: 0.5rem;">
                    ${revertButtonHtml}
                    <button class="std-button ${newValidationColor}" onclick="window.resetPage()" style="flex: 1;">
                        <span class="button-text">🔄 New Validation</span>
                    </button>
                </div>
            `;
            
            // Add event listeners for the buttons after DOM update
            setTimeout(() => {
                const downloadBtn = document.getElementById(`${cardId}-download-btn`);
                const refineBtn = document.getElementById(`${cardId}-refine-btn`);
                const revertBtn = document.getElementById(`${cardId}-revert-btn`);
                const balanceInfo = document.getElementById(`${cardId}-balance-info`);

                if (refineBtn) {
                    refineBtn.addEventListener('click', debounceConfigAction('refine-config-2', async () => {
                        try {
                            await window.createRefinementCard();
                        } catch (error) {
                            console.error('Refine error:', error);
                        }
                    }));
                }

                // Only add revert button listener if the button exists (version > 1)
                if (revertBtn) {
                    revertBtn.addEventListener('click', debounceConfigAction('revert-config-completion', async () => {
                        try {
                            revertBtn.disabled = true;
                            await createConfigCardWithId('last');
                        } catch (error) {
                            console.error('Revert error:', error);
                            alert('Revert failed: ' + error.message);
                        } finally {
                            revertBtn.disabled = false;
                        }
                    }));
                }

                // Handle download preparation
                // Enable download button after a short delay (file is generated during validation)
                if (downloadBtn && balanceInfo) {
                    setTimeout(() => {
                        if (downloadBtn) {
                            downloadBtn.disabled = false;
                            downloadBtn.querySelector('.button-text').textContent = '📥 Download Results';

                            downloadBtn.addEventListener('click', async function() {
                                try {
                                    markDownloadStart();
                                    await window.downloadValidationResults();
                                } catch (error) {
                                    console.error('Download error:', error);
                                    alert('Download failed: ' + error.message);
                                }
                            });
                        }

                        // Update balance display
                        if (balanceInfo && globalState.accountBalance !== undefined) {
                            balanceInfo.textContent = `• Remaining balance: $${globalState.accountBalance.toFixed(2)}`;
                        }
                    }, 3000); // 3 second delay for download to be ready
                }
            }, 0);
            }
        }, showResultsDelay);

    } else if (data.status === 'FAILED' || data.status === 'ERROR') {
        completeThinkingInCard(cardId, 'Validation failed');

        const errorMessage = data.error_message || data.verbose_status || 'Validation failed';
        showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');
        console.error('Validation failed:', data);

        // Reset guard flag on error
        globalState.processingInProgress = false;
    }
}

// 7. Completion Card
function createCompletionCard(completionData) {
// If status is COMPLETED, trust the backend - don't check row counts
const isPartial = completionData.status !== 'COMPLETED' && 
                 completionData.total_rows && globalState.processedRows < completionData.total_rows;

const cardId = generateCardId();
let content = '';
let buttons = [];

if (isPartial) {
    content = `
        <p style="margin-bottom: 1.5rem; color: var(--text-secondary);">
            You have processed ${globalState.processedRows} of ${completionData.total_rows} total rows.
        </p>
        <div class="form-group">
            <label class="form-label" for="${cardId}-max-rows">Total Rows to Process</label>
            <input type="number" id="${cardId}-max-rows" class="form-input" 
                    placeholder="Enter new total row count" min="${globalState.processedRows + 1}">
            <p style="font-size: var(--font-size-small); color: var(--text-secondary); margin-top: 0.5rem;">
                This is the total number of rows from the top, not additional rows. Leave empty to process all.
            </p>
        </div>
        <div id="${cardId}-messages"></div>
    `;

    buttons = [
        {
            text: 'Continue Processing',
            icon: '▶️',
            variant: 'primary',
            width: 1,
            callback: async () => {
                const maxRows = document.getElementById(`${cardId}-max-rows`).value;
                await continueProcessing(cardId, maxRows);
            }
        },
        {
            text: 'New Validation',
            icon: '🔄',
            variant: 'secondary',
            width: 1,
            callback: () => window.resetPage()
        }
    ];
} else {
    // Show full content immediately with disabled download button
    const balanceText = globalState.accountBalance !== undefined ? 
        `• Remaining balance: $${globalState.accountBalance.toFixed(2)}` : 
        `• Balance updating...`;
    
    content = `
        <div class="message message-success" style="margin-bottom: 1rem;">
            <span class="message-icon">🎉</span>
            <div style="line-height: 1.6;">
                <div style="margin-bottom: 8px;">
                    • Your validation has been completed successfully and emailed to you
                </div>
                <div style="margin-bottom: 8px;">
                    • Notice the Updated and Original sheets, color coded by confidence: Green (High), Yellow (Medium), Red (Low), No Color (Null/Blank)
                </div>
                <div style="margin-bottom: 8px;">
                    • If you want to change anything, refine the configuration and check out the preview
                </div>
                <div id="${cardId}-balance-info">
                    ${balanceText}
                </div>
            </div>
        </div>
    `;

    // Check if revert button should be shown (only if this session has 2+ versions)
    const sessionVersionCount = completionData.session_version_count || 0;
    const currentVersion = completionData.config_version || globalState.currentConfig?.config_version || 1;
    const showRevertButton = sessionVersionCount >= 2;

    buttons = [
        {
            text: 'Preparing Download...',
            icon: '📥',
            variant: 'primary',
            width: 'half',
            disabled: true,
            callback: async function() {} // Will be replaced when enabled
        },
        {
            text: 'Refine Configuration',
            icon: '🔧',
            variant: 'secondary',
            width: 'half',
            callback: async function() {
                try {
                    await window.createRefinementCard();
                } catch (error) {
                    console.error('Refine error:', error);
                    alert('Refine failed: ' + error.message);
                }
            }
        }
    ];

    // Only add revert button if version > 1
    if (showRevertButton) {
        buttons.push({
            text: 'Revert to Previous',
            icon: '↩️',
            variant: 'secondary',
            width: 'half',
            callback: async function() {
                try {
                    await createConfigCardWithId('last');
                } catch (error) {
                    console.error('Revert error:', error);
                    alert('Revert failed: ' + error.message);
                }
            }
        });
    }

    buttons.push({
        text: 'New Validation',
        icon: '🔄',
        variant: 'secondary',
        width: 'full',
        callback: () => window.resetPage()
    });
}

const card = createCard({
    icon: isPartial ? '📈' : '🎉',
    title: isPartial ? 'Continue Validation' : 'Process',
    subtitle: isPartial ? 'Process more of your table' : 'Ready to start a new validation',
    content,
    buttons
});

// If this is a completion (not partial), add delayed update to enable download and update balance
if (!isPartial) {
    setTimeout(() => {
        // Find and enable the download button
        const downloadButton = card.querySelector('button[disabled]');
        const balanceElement = card.querySelector(`#${card.id}-balance-info`);
        
        if (downloadButton) {
            downloadButton.disabled = false;
            downloadButton.querySelector('.button-text').textContent = '📥 Download Results';
            
            // Add the click handler
            downloadButton.addEventListener('click', async function() {
                try {
                    markDownloadStart();
                    await window.downloadValidationResults();
                } catch (error) {
                    console.error('Download error:', error);
                    alert('Download failed: ' + error.message);
                }
            });
        }
        
        // Update balance display if we have it
        if (balanceElement && globalState.accountBalance !== undefined) {
            balanceElement.textContent = `• Remaining balance: $${globalState.accountBalance.toFixed(2)}`;
        }
    }, 5000); // 5 second delay for download to be ready
}

return card;
}

async function continueProcessing(cardId, maxRows) {
    // Validate input
    if (maxRows && parseInt(maxRows) <= globalState.processedRows) {
        showMessage(`${cardId}-messages`,
            `Please enter a number greater than ${globalState.processedRows}`,
            'error'
        );
        return;
    }

    // Create new processing card
    createProcessingCard();
}
