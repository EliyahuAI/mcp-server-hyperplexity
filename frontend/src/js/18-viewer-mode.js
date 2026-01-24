/* ========================================
 * 18-viewer-mode.js - Results Viewer Mode
 *
 * Provides standalone viewer for validation results.
 * Can be used as:
 * 1. Standalone mode via URL: ?mode=viewer&session=xxx&version=1
 * 2. As a card within the app: createResultsViewerCard(options)
 *
 * Dependencies: 00-config.js, 04-cards.js, 07-email-validation.js,
 *               16-interactive-table.js, 17-table-view-card.js
 * ======================================== */

/**
 * Initialize viewer mode (called from 99-init.js when mode=viewer detected)
 * Requires email validation, then loads and displays the results
 */
function initViewerMode() {
    const params = getViewerParams();

    // Validate we have required parameters
    if (!params.session && !params.path) {
        // No session or path specified - show error
        const cardId = generateCardId();
        createCard({
            id: cardId,
            icon: '⚠️',
            title: 'Missing Parameters',
            subtitle: 'No results specified',
            content: `
                <div class="message message-error">
                    <span class="message-icon">⚠️</span>
                    <span>Please provide a session ID or path in the URL.</span>
                </div>
                <p style="margin-top: 1rem; color: var(--text-secondary);">
                    Example: <code>?mode=viewer&session=session_20240124_abc123</code>
                </p>
            `
        });
        return;
    }

    // Require email validation before showing results
    requireEmailThen(() => {
        loadAndDisplayResults(params);
    }, 'view your results');
}

/**
 * Load results from API or local file and display in viewer card
 * @param {Object} params - { session, version, path }
 */
async function loadAndDisplayResults(params) {
    // Create the viewer card
    const { cardId } = createResultsViewerCard({
        title: 'Validation Results',
        subtitle: params.session ? `Session: ${params.session}` : (params.path || 'Loading...'),
        infoHeaderText: 'View your validation results. Click cells for details, or download the full Excel file.'
    });

    // Show loading state
    showThinkingInCard(cardId, 'Loading results...', true);

    try {
        let data;

        // If path parameter provided and looks like a local file, try loading directly
        if (params.path && (params.path.endsWith('.json') || params.path.startsWith('./'))) {
            console.log('[VIEWER] Loading from local path:', params.path);
            const response = await fetch(params.path);
            if (!response.ok) {
                throw new Error(`Failed to load local file: ${response.status}`);
            }
            const table_metadata = await response.json();
            data = {
                success: true,
                table_metadata,
                table_name: params.path.split('/').pop().replace('.json', '')
            };
        } else {
            // Fetch metadata from API
            const response = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'getViewerData',
                    email: globalState.email,
                    session_id: params.session,
                    version: params.version,
                    path: params.path
                })
            });

            data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || data.message || 'Failed to load results');
            }
        }

        // Hide loading indicator
        completeThinkingInCard(cardId, 'Results loaded');

        // Update card subtitle with actual info
        const card = document.getElementById(cardId);
        if (card && data.table_name) {
            const subtitle = card.querySelector('.card-subtitle');
            if (subtitle) {
                subtitle.textContent = data.table_name;
            }
        }

        // Display results in the card
        displayResultsInCard(cardId, data);

    } catch (error) {
        console.error('[VIEWER] Error loading results:', error);
        completeThinkingInCard(cardId, 'Error loading results');
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

/**
 * Create a results viewer card (can be called from anywhere in the app)
 *
 * @param {Object} options - Card options
 * @param {string} options.cardId - Optional explicit card ID
 * @param {string} options.title - Card title (default: 'Validation Results')
 * @param {string} options.subtitle - Card subtitle
 * @param {string} options.infoHeaderText - Info header text
 * @param {Object} options.tableMetadata - Optional pre-loaded table metadata
 * @param {string} options.downloadUrl - Optional download URL
 * @returns {Object} { cardId, element }
 */
function createResultsViewerCard(options = {}) {
    const cardId = options.cardId || generateCardId();

    const content = `
        <div id="${cardId}-info-header" class="message message-info" style="display: flex;">
            <span class="message-icon">ℹ️</span>
            <span id="${cardId}-info-text">${options.infoHeaderText || 'View your validation results below.'}</span>
        </div>
        <div id="${cardId}-table-container"></div>
        <div id="${cardId}-messages"></div>
        <div id="${cardId}-buttons" class="card-buttons"></div>
    `;

    const card = createCard({
        id: cardId,
        icon: '📊',
        title: options.title || 'Validation Results',
        subtitle: options.subtitle || '',
        content,
        buttons: []  // Buttons added after data loads
    });

    // If pre-loaded metadata provided, display immediately
    if (options.tableMetadata) {
        displayResultsInCard(cardId, {
            table_metadata: options.tableMetadata,
            download_url: options.downloadUrl
        });
    }

    return { cardId, element: card };
}

/**
 * Display results data in a viewer card
 *
 * @param {string} cardId - Card ID to update
 * @param {Object} data - Results data from API
 * @param {Object} data.table_metadata - Table metadata for InteractiveTable
 * @param {string} data.download_url - URL to download Excel file
 * @param {string} data.enhanced_download_url - Alternative download URL
 * @param {string} data.json_download_url - URL to download JSON metadata
 */
function displayResultsInCard(cardId, data) {
    const container = document.getElementById(`${cardId}-table-container`);
    if (!container) {
        console.error(`[VIEWER] Container ${cardId}-table-container not found`);
        return;
    }

    // Render table if metadata available
    if (data.table_metadata && typeof InteractiveTable !== 'undefined') {
        const tableHtml = InteractiveTable.render(data.table_metadata, {
            showGeneralNotes: true,
            showLegend: true
        });
        container.innerHTML = tableHtml;
        InteractiveTable.init();
    } else if (data.markdown_table) {
        // Fallback to markdown table
        container.innerHTML = renderMarkdown(data.markdown_table);
    } else {
        container.innerHTML = '<p class="table-empty-message">No table data available.</p>';
    }

    // Determine download URLs
    const excelUrl = data.enhanced_download_url || data.download_url;
    const jsonUrl = data.json_download_url;

    // Build download buttons
    const buttons = [
        {
            text: '📥 Download Excel',
            icon: '📥',
            variant: 'primary',
            callback: async (e) => {
                const button = e.target.closest('button');
                if (excelUrl) {
                    markButtonSelected(button, '📥 Downloading...');
                    window.location.href = excelUrl;
                    setTimeout(() => markButtonUnselected(button), 2000);
                } else {
                    // Request download URL from API
                    await downloadResultsViaApi(cardId, button, 'excel');
                }
            }
        },
        {
            text: '📋 Download JSON',
            icon: '📋',
            variant: 'secondary',
            callback: async (e) => {
                const button = e.target.closest('button');
                if (jsonUrl) {
                    markButtonSelected(button, '📋 Downloading...');
                    window.location.href = jsonUrl;
                    setTimeout(() => markButtonUnselected(button), 2000);
                } else if (data.table_metadata) {
                    // Generate JSON download from current metadata
                    downloadJsonMetadata(data.table_metadata, button);
                } else {
                    await downloadResultsViaApi(cardId, button, 'json');
                }
            }
        }
    ];

    createButtonRow(`${cardId}-buttons`, buttons);
}

/**
 * Download table metadata as JSON file
 * @param {Object} metadata - Table metadata object
 * @param {HTMLElement} button - Button element for state updates
 */
function downloadJsonMetadata(metadata, button) {
    try {
        markButtonSelected(button, '📋 Preparing...');

        const jsonStr = JSON.stringify(metadata, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = 'table_metadata.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        markButtonSelected(button, '📋 Downloaded!');
        setTimeout(() => markButtonUnselected(button), 2000);
    } catch (error) {
        console.error('[VIEWER] JSON download error:', error);
        markButtonUnselected(button);
    }
}

/**
 * Download results via API call (when direct URL not available)
 *
 * @param {string} cardId - Card ID for showing messages
 * @param {HTMLElement} button - Button element to update state
 * @param {string} fileType - Type of file to download: 'excel' or 'json'
 */
async function downloadResultsViaApi(cardId, button, fileType = 'excel') {
    const params = getViewerParams();
    const icon = fileType === 'json' ? '📋' : '📥';

    try {
        markButtonSelected(button, `${icon} Preparing download...`);

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'getViewerData',
                email: globalState.email,
                session_id: params.session || globalState.sessionId,
                version: params.version
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to get download URL');
        }

        // Get appropriate download URL
        let downloadUrl;
        if (fileType === 'json') {
            downloadUrl = data.json_download_url;
            // Fallback: generate from metadata if no URL provided
            if (!downloadUrl && data.table_metadata) {
                downloadJsonMetadata(data.table_metadata, button);
                return;
            }
        } else {
            downloadUrl = data.enhanced_download_url || data.download_url;
        }

        if (!downloadUrl) {
            throw new Error(`No ${fileType} download available`);
        }

        // Trigger download
        window.location.href = downloadUrl;
        markButtonSelected(button, `${icon} Downloading...`);
        setTimeout(() => markButtonUnselected(button), 2000);

    } catch (error) {
        console.error('[VIEWER] Download error:', error);
        showMessage(`${cardId}-messages`, `Download failed: ${error.message}`, 'error');
        markButtonUnselected(button);
    }
}

/**
 * Show full validation results after processing completes
 * Called from validation flow when results are ready
 *
 * @param {Object} validationData - Full validation result data
 * @param {Object} validationData.table_metadata - Table metadata
 * @param {string} validationData.download_url - Download URL
 * @param {string} validationData.table_name - Table name for subtitle
 * @param {number} validationData.row_count - Number of rows processed
 */
function showFullValidationResults(validationData) {
    const { cardId } = createResultsViewerCard({
        title: 'Validation Complete',
        subtitle: validationData.table_name
            ? `${validationData.table_name} - ${validationData.row_count || ''} rows`
            : 'Your results are ready',
        infoHeaderText: 'Validation complete! Review your results below or download the full Excel file.',
        tableMetadata: validationData.table_metadata,
        downloadUrl: validationData.enhanced_download_url || validationData.download_url
    });

    // Show success message
    showMessage(`${cardId}-messages`, 'Validation completed successfully!', 'success');

    return cardId;
}
