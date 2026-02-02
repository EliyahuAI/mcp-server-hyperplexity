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
            // SECURITY: Get session token from sessionStorage
            const sessionToken = sessionStorage.getItem('sessionToken');

            // Fetch metadata from API
            const requestHeaders = { 'Content-Type': 'application/json' };
            const requestBody = {
                action: 'getViewerData',
                session_id: params.session,
                version: params.version,
                path: params.path
            };

            // SECURITY: Prefer session token in header, fallback to email in body for backward compatibility
            if (sessionToken) {
                requestHeaders['X-Session-Token'] = sessionToken;
            } else {
                // Legacy: include email in body if no token available
                requestBody.email = globalState.email;
            }

            const response = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                headers: requestHeaders,
                body: JSON.stringify(requestBody)
            });

            data = await response.json();

            // SECURITY: Handle token revocation
            if (data.token_revoked) {
                logger.error('[SECURITY] Token revoked by server - clearing session');

                // Clear session data
                sessionStorage.removeItem('sessionToken');
                localStorage.removeItem('validatedEmail');
                globalState.sessionToken = null;
                globalState.email = null;

                // Hide signed-in badge if function exists
                if (typeof hideSignedInBadge === 'function') {
                    hideSignedInBadge();
                }

                // Show security warning
                hideThinkingInCard(cardId);
                updateCardContent(cardId, `
                    <div class="message message-error">
                        <span class="message-icon">⚠️</span>
                        <span><strong>Security Alert:</strong> ${data.error || 'Your session has been revoked due to suspicious activity.'}</span>
                    </div>
                    <div style="margin-top: 1rem; color: var(--text-secondary);">
                        <p>Please validate your email again to continue.</p>
                        <button onclick="location.reload()" style="margin-top: 1rem;">
                            Reload Page
                        </button>
                    </div>
                `);
                return;
            }

            if (!response.ok || !data.success) {
                throw new Error(data.error || data.message || 'Failed to load results');
            }
        }

        // Hide loading indicator
        completeThinkingInCard(cardId, 'Results loaded');

        // Debug: log the data received from API
        console.log('[VIEWER] Data received:', {
            clean_table_name: data.clean_table_name,
            table_name: data.table_name,
            analysis_date: data.analysis_date,
            is_full_validation: data.is_full_validation,
            version: data.version
        });

        // Update card title and subtitle with clean table name and date
        const card = document.getElementById(cardId);
        console.log('[VIEWER] Card element:', card, 'cardId:', cardId);

        if (card) {
            // Use clean_table_name for the title if available
            const displayName = data.clean_table_name || data.table_name || 'Validation Results';
            const titleEl = card.querySelector('.card-title');
            console.log('[VIEWER] Title element:', titleEl, 'displayName:', displayName);
            if (titleEl) {
                titleEl.textContent = displayName;
            }

            // Build subtitle with analysis date and validation type
            let subtitleParts = [];
            if (data.analysis_date) {
                const dateObj = new Date(data.analysis_date);
                const formattedDate = dateObj.toLocaleDateString('en-US', {
                    year: 'numeric', month: 'short', day: 'numeric'
                });
                subtitleParts.push(`Analyzed: ${formattedDate}`);
            }
            if (data.is_full_validation !== undefined) {
                subtitleParts.push(data.is_full_validation ? 'Full Validation' : 'Preview');
            }
            if (data.version) {
                subtitleParts.push(`v${data.version}`);
            }
            console.log('[VIEWER] Subtitle parts:', subtitleParts);

            const subtitle = card.querySelector('.card-subtitle');
            console.log('[VIEWER] Subtitle element:', subtitle);
            if (subtitle && subtitleParts.length > 0) {
                subtitle.textContent = subtitleParts.join(' • ');
                console.log('[VIEWER] Updated subtitle to:', subtitleParts.join(' • '));
            } else if (!subtitle) {
                console.warn('[VIEWER] No subtitle element found, creating one');
                // Create subtitle if it doesn't exist
                const headerDiv = card.querySelector('.card-header > div:nth-child(2)');
                if (headerDiv) {
                    const newSubtitle = document.createElement('p');
                    newSubtitle.className = 'card-subtitle';
                    newSubtitle.textContent = subtitleParts.join(' • ');
                    headerDiv.appendChild(newSubtitle);
                }
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
        <div id="${cardId}-buttons" class="card-buttons"></div>
        <div id="${cardId}-messages"></div>
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

    // Update the info header with analysis date if available
    const infoText = document.getElementById(`${cardId}-info-text`);
    if (infoText && data.analysis_date) {
        const dateObj = new Date(data.analysis_date);
        const formattedDate = dateObj.toLocaleDateString('en-US', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
        const validationType = data.is_full_validation ? 'Full validation' : 'Preview';
        infoText.innerHTML = `<strong>${validationType} completed ${formattedDate}</strong>. Click cells for details, or download the results.`;
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
            text: 'Download Excel',
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
            text: 'Download JSON',
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
        },
        {
            text: 'Update Table',
            icon: '🔄',
            variant: 'tertiary',
            callback: async (e) => {
                const button = e.target.closest('button');
                await handleUpdateTable(cardId, button, data);
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

// ============================================
// DEMO MODE (PUBLIC TABLES - NO EMAIL REQUIRED)
// ============================================

/**
 * Initialize demo mode (called from 99-init.js when ?demo= detected)
 * No email required - loads public demo table directly
 */
function initDemoMode() {
    const params = getDemoParams();

    if (!params.tableName) {
        // No table name specified - show error
        const cardId = generateCardId();
        createCard({
            id: cardId,
            icon: '📊',
            title: 'Demo Not Found',
            subtitle: 'No demo table specified',
            content: `
                <div class="message message-error">
                    <span class="message-icon">⚠️</span>
                    <span>Please provide a demo table name in the URL.</span>
                </div>
                <p style="margin-top: 1rem; color: var(--text-secondary);">
                    Example: <code>?demo=example-table</code>
                </p>
            `
        });
        return;
    }

    // Load demo directly - no email required
    loadAndDisplayDemo(params.tableName);
}

/**
 * Load demo table from S3 demos folder
 * @param {string} tableName - Name of the demo table to load
 */
async function loadAndDisplayDemo(tableName) {
    // Create the viewer card
    const { cardId } = createResultsViewerCard({
        title: 'Demo Table',
        subtitle: `Loading ${tableName}...`,
        infoHeaderText: 'Explore this demo table. Click cells for details.'
    });

    // Show loading state
    showThinkingInCard(cardId, 'Loading demo...', true);

    try {
        // Call backend to get demo data (no email required)
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'getDemoData',
                table_name: tableName
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Demo not found');
        }

        // Hide loading indicator
        completeThinkingInCard(cardId, 'Demo loaded');

        // Update card title with clean name
        const card = document.getElementById(cardId);
        if (card) {
            const titleEl = card.querySelector('.card-title');
            if (titleEl) {
                titleEl.textContent = data.clean_table_name || tableName;
            }
            const subtitleEl = card.querySelector('.card-subtitle');
            if (subtitleEl) {
                subtitleEl.textContent = 'Public Demo Table';
            }
        }

        // Display demo results with special button handling
        displayDemoResultsInCard(cardId, data, tableName);

    } catch (error) {
        console.error('[DEMO] Error loading demo:', error);
        completeThinkingInCard(cardId, 'Error loading demo');
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

/**
 * Display demo results with special button handling
 * Downloads work without email, "Create Your Own Table" requires email
 *
 * @param {string} cardId - Card ID to update
 * @param {Object} data - Demo data from API
 * @param {string} tableName - Original table name for downloads
 */
function displayDemoResultsInCard(cardId, data, tableName) {
    const container = document.getElementById(`${cardId}-table-container`);
    if (!container) {
        console.error(`[DEMO] Container ${cardId}-table-container not found`);
        return;
    }

    // Update the info header
    const infoText = document.getElementById(`${cardId}-info-text`);
    if (infoText) {
        infoText.innerHTML = '<strong>Demo Table</strong> - Click cells for details, or create your own validated table.';
    }

    // Render table if metadata available
    if (data.table_metadata && typeof InteractiveTable !== 'undefined') {
        const tableHtml = InteractiveTable.render(data.table_metadata, {
            showGeneralNotes: true,
            showLegend: true
        });
        container.innerHTML = tableHtml;
        InteractiveTable.init();
    } else {
        container.innerHTML = '<p class="table-empty-message">No table data available.</p>';
        // Still show "Create Your Own" button even if no table data
    }

    // Build buttons - Create Your Own requires email
    const buttons = [
        {
            text: 'Download JSON',
            icon: '📋',
            variant: 'secondary',
            callback: (e) => {
                const button = e.target.closest('button');
                downloadJsonMetadata(data.table_metadata, button);
            }
        },
        {
            text: 'Create Your Own Table',
            icon: '✨',
            variant: 'primary',
            callback: () => {
                // Show Get Started card (handles email validation itself)
                if (typeof createUploadOrDemoCard === 'function') {
                    createUploadOrDemoCard();
                } else {
                    // Fallback: redirect to main app
                    window.location.href = window.location.pathname;
                }
            }
        }
    ];

    createButtonRow(`${cardId}-buttons`, buttons);
}

/**
 * Handle the Update Table button click.
 * Creates a new validation session from the current enhanced results.
 *
 * @param {string} cardId - Card ID for showing messages
 * @param {HTMLElement} button - Button element for state updates
 * @param {Object} data - Results data containing session info
 */
async function handleUpdateTable(cardId, button, data) {
    const params = getViewerParams();

    try {
        markButtonSelected(button, '🔄 Creating session...');

        // Call backend to create update session
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'createUpdateSession',
                email: globalState.email,
                source_session_id: params.session || data.session_id,
                source_version: params.version || data.version
            })
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || 'Failed to create update session');
        }

        console.log('[VIEWER] Update session created:', result.new_session_id);

        // Warn if only preview data was available
        if (result.used_preview_data) {
            console.warn('[VIEWER] Using preview data - full validation not found');
            showMessage(`${cardId}-messages`,
                'Warning: Using preview data. Run a full validation first for complete results.', 'warning');
        }

        // Update global state for new session
        globalState.sessionId = result.new_session_id;
        globalState.excelFileUploaded = true;
        globalState.configStored = result.config_copied;
        globalState.activePreviewCard = null;

        markButtonSelected(button, '🔄 Starting preview...');
        showMessage(`${cardId}-messages`,
            'New session created. Starting preview...', 'success');

        // Clear viewer URL params and trigger preview after a short delay
        setTimeout(() => {
            // Remove viewer mode params from URL
            window.history.replaceState({}, '', window.location.pathname);

            // Create and start the preview card
            if (typeof createPreviewCard === 'function') {
                createPreviewCard();
            } else {
                console.error('[VIEWER] createPreviewCard function not available');
                showMessage(`${cardId}-messages`,
                    'Session created but preview could not start automatically. Please refresh the page.', 'warning');
            }
        }, 1000);

    } catch (error) {
        console.error('[VIEWER] Update table error:', error);
        showMessage(`${cardId}-messages`, `Update failed: ${error.message}`, 'error');
        markButtonUnselected(button);
    }
}
