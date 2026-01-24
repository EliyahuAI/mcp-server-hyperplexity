/* ========================================
 * 17-table-view-card.js - Flexible Table View Card
 *
 * Creates a card component for displaying table data from:
 * - Preview validation results
 * - Full validation results (with live updates)
 * - Static results viewing
 *
 * Uses InteractiveTable module for rendering and existing
 * card/button system for actions.
 *
 * Dependencies: 04-cards.js (createCard, createButtonRow, showThinkingInCard)
 *               16-interactive-table.js (InteractiveTable)
 * ======================================== */

/**
 * Create a table view card that can show:
 * - Live processing progress with table updating
 * - Static table results
 * - Cost estimates and action buttons
 *
 * @param {Object} options - Card options
 * @param {string} options.cardId - Optional explicit card ID
 * @param {string} options.icon - Card icon (default: '📊')
 * @param {string} options.title - Card title (default: 'Table Results')
 * @param {string} options.subtitle - Card subtitle
 * @param {boolean} options.showInfoHeader - Show info header above table (default: true)
 * @param {string} options.infoHeaderText - Info header text
 * @returns {Object} Object with cardId and DOM element
 */
function createTableViewCard(options = {}) {
    const cardId = options.cardId || generateCardId();

    // Build content with placeholders for table, info panel, messages, buttons
    const content = `
        <div id="${cardId}-info-header" class="message message-info" style="display: ${options.showInfoHeader !== false ? 'flex' : 'none'};">
            <span class="message-icon">ℹ️</span>
            <span id="${cardId}-info-text">${options.infoHeaderText || 'Table data preview.'}</span>
        </div>
        <div id="${cardId}-progress"></div>
        <div id="${cardId}-table-container"></div>
        <div id="${cardId}-cost-estimate" class="cost-estimate" style="display: none;">
            <div class="cost-estimate-header">Estimates for Processing Entire Table</div>
            <div class="cost-estimate-items" id="${cardId}-estimates"></div>
        </div>
        <div id="${cardId}-messages"></div>
        <div id="${cardId}-buttons" class="card-buttons"></div>
    `;

    const card = createCard({
        icon: options.icon || '📊',
        title: options.title || 'Table Results',
        subtitle: options.subtitle || '',
        content,
        id: cardId
    });

    return { cardId, element: card };
}

/**
 * Update table view card with new table data
 *
 * @param {string} cardId - Card ID to update
 * @param {Object} tableMetadata - Table metadata for InteractiveTable.render()
 * @param {Object} options - Update options
 * @param {boolean} options.showGeneralNotes - Show general notes box (default: true)
 * @param {boolean} options.showLegend - Show confidence legend (default: true)
 * @param {number} options.maxRows - Maximum rows to display
 * @param {Array} options.buttons - Button configurations for createButtonRow
 * @param {string} options.infoHeaderText - Update info header text
 * @param {boolean} options.hideInfoHeader - Hide the info header
 */
function updateTableViewCard(cardId, tableMetadata, options = {}) {
    const container = document.getElementById(`${cardId}-table-container`);
    if (!container) {
        console.error(`[TABLE_VIEW_CARD] Container ${cardId}-table-container not found`);
        return;
    }

    // Hide progress indicator if showing
    const progress = document.getElementById(`${cardId}-progress`);
    if (progress) {
        progress.innerHTML = '';
    }

    // Update info header if specified
    if (options.infoHeaderText) {
        const infoText = document.getElementById(`${cardId}-info-text`);
        if (infoText) {
            infoText.textContent = options.infoHeaderText;
        }
    }

    // Hide/show info header
    const infoHeader = document.getElementById(`${cardId}-info-header`);
    if (infoHeader) {
        infoHeader.style.display = options.hideInfoHeader ? 'none' : 'flex';
    }

    // Render table using InteractiveTable module
    if (tableMetadata && typeof InteractiveTable !== 'undefined') {
        const tableHtml = InteractiveTable.render(tableMetadata, {
            showGeneralNotes: options.showGeneralNotes !== false,
            showLegend: options.showLegend !== false,
            maxRows: options.maxRows
        });
        container.innerHTML = tableHtml;
        InteractiveTable.init();
    } else if (tableMetadata && typeof InteractiveTable === 'undefined') {
        // InteractiveTable module not loaded - show error
        console.error('[TABLE_VIEW_CARD] InteractiveTable module not loaded');
        container.innerHTML = '<p class="table-empty-message" style="color: #c62828;">Error: Table rendering module not loaded. Please refresh the page.</p>';
    } else if (!tableMetadata) {
        container.innerHTML = '<p class="table-empty-message">No table data available.</p>';
    }

    // Update buttons using existing card button system
    if (options.buttons && options.buttons.length > 0) {
        createButtonRow(`${cardId}-buttons`, options.buttons);
    }
}

/**
 * Show processing progress in table view card
 *
 * @param {string} cardId - Card ID
 * @param {string} message - Progress message
 * @param {boolean} withProgress - Show progress bar
 */
function showTableProgress(cardId, message = 'Processing...', withProgress = false) {
    showThinkingInCard(cardId, message, withProgress);
}

/**
 * Hide processing progress in table view card
 *
 * @param {string} cardId - Card ID
 */
function hideTableProgress(cardId) {
    hideThinkingInCard(cardId);
}

/**
 * Show cost estimates in table view card
 *
 * @param {string} cardId - Card ID
 * @param {Object} costData - Cost data object
 * @param {number} costData.totalRows - Total rows
 * @param {number} costData.validatedColumnsCount - Columns to validate
 * @param {number} costData.totalAICalls - Total AI calls
 * @param {number} costData.estimatedTime - Estimated time in seconds
 * @param {number} costData.estimatedCost - Estimated cost
 * @param {number} costData.discount - Discount amount
 * @param {number} costData.effectiveCost - Cost after discount
 * @param {Object} costData.accountInfo - Account balance info
 */
function showTableCostEstimates(cardId, costData) {
    const costEl = document.getElementById(`${cardId}-cost-estimate`);
    const estimatesEl = document.getElementById(`${cardId}-estimates`);

    if (!costEl || !estimatesEl) {
        console.warn(`[TABLE_VIEW_CARD] Cost estimate elements not found for ${cardId}`);
        return;
    }

    costEl.style.display = 'block';

    let estimatesHtml = '';

    if (costData.totalRows > 0) {
        estimatesHtml += `<div class="cost-item"><span class="cost-label">Total Rows</span><span class="cost-value">${costData.totalRows.toLocaleString()}</span></div>`;
    }

    if (costData.validatedColumnsCount) {
        estimatesHtml += `<div class="cost-item"><span class="cost-label">Columns to Validate</span><span class="cost-value">${costData.validatedColumnsCount}</span></div>`;
    }

    if (costData.totalAICalls > 0) {
        estimatesHtml += `<div class="cost-item"><span class="cost-label">Total AI Calls</span><span class="cost-value">${costData.totalAICalls.toLocaleString()}</span></div>`;
    }

    if (costData.estimatedTime > 0) {
        estimatesHtml += `<div class="cost-item"><span class="cost-label">Est. Time</span><span class="cost-value">${Math.ceil(costData.estimatedTime / 60)} min</span></div>`;
    }

    // Display cost with discount if applicable
    if (costData.estimatedCost !== undefined) {
        if (costData.discount > 0) {
            estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost → Discounted</span><span class="cost-value"><span style="text-decoration: line-through; color: #999;">$${costData.estimatedCost.toFixed(2)}</span> → $${costData.effectiveCost.toFixed(2)}</span></div>`;
        } else {
            estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost</span><span class="cost-value">$${costData.estimatedCost.toFixed(2)}</span></div>`;
        }
    }

    // Add account balance information if available
    if (costData.accountInfo) {
        const currentBalance = costData.accountInfo.current_balance || 0;
        const sufficientBalance = costData.accountInfo.sufficient_balance ?? true;
        const creditsNeeded = costData.accountInfo.credits_needed || 0;

        estimatesHtml += `<hr style="margin: 10px 0; border: none; border-top: 1px solid #eee;">`;
        estimatesHtml += `<div class="cost-item"><span class="cost-label">Your Balance</span><span class="cost-value">$${currentBalance.toFixed(2)}</span></div>`;

        if (!sufficientBalance && creditsNeeded > 0) {
            estimatesHtml += `<div class="cost-item"><span class="cost-label" style="color: #f44336;">Credits Needed</span><span class="cost-value" style="color: #f44336;">$${creditsNeeded.toFixed(2)}</span></div>`;
        }
    }

    estimatesEl.innerHTML = estimatesHtml;
}

/**
 * Hide cost estimates in table view card
 *
 * @param {string} cardId - Card ID
 */
function hideTableCostEstimates(cardId) {
    const costEl = document.getElementById(`${cardId}-cost-estimate`);
    if (costEl) {
        costEl.style.display = 'none';
    }
}

/**
 * Update card subtitle
 *
 * @param {string} cardId - Card ID
 * @param {string} subtitle - New subtitle text
 */
function updateTableViewCardSubtitle(cardId, subtitle) {
    const card = document.getElementById(cardId);
    if (!card) return;

    const subtitleEl = card.querySelector('.card-subtitle');
    if (subtitleEl) {
        subtitleEl.textContent = subtitle;
    }
}

/**
 * Update card title
 *
 * @param {string} cardId - Card ID
 * @param {string} title - New title text
 */
function updateTableViewCardTitle(cardId, title) {
    const card = document.getElementById(cardId);
    if (!card) return;

    const titleEl = card.querySelector('.card-title');
    if (titleEl) {
        titleEl.textContent = title;
    }
}

/**
 * Show a message in the table view card
 *
 * @param {string} cardId - Card ID
 * @param {string} message - Message text
 * @param {string} type - Message type ('info', 'success', 'error', 'warning')
 */
function showTableViewMessage(cardId, message, type = 'info') {
    showMessage(`${cardId}-messages`, message, type);
}

/**
 * Clear messages in the table view card
 *
 * @param {string} cardId - Card ID
 */
function clearTableViewMessages(cardId) {
    const messagesEl = document.getElementById(`${cardId}-messages`);
    if (messagesEl) {
        messagesEl.innerHTML = '';
    }
}
