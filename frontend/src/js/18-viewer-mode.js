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
    // Add viewer-mode class for wider container
    document.body.classList.add('viewer-mode');

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
            const requestBody = {
                action: 'getViewerData',
                session_id: params.session,
                version: params.version,
                path: params.path
            };

            const response = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify(requestBody)
            });

            data = await response.json();

            // SECURITY: Handle token revocation
            if (data.token_revoked) {
                console.error('[SECURITY] Token revoked by server - clearing session');

                // Clear session data
                localStorage.removeItem('sessionToken');
                localStorage.removeItem('validatedEmail');
                sessionStorage.removeItem('validatedEmail');
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
        await displayResultsInCard(cardId, data);

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
 * @param {boolean} data.metadata_too_large - If true, metadata needs to be fetched separately
 * @param {string} data.download_url - URL to download Excel file
 * @param {string} data.enhanced_download_url - Alternative download URL
 * @param {string} data.json_download_url - URL to download JSON metadata
 */
async function displayResultsInCard(cardId, data) {
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

    // If metadata was too large to include inline, fetch it from S3
    if (data.metadata_too_large && data.json_download_url && !data.table_metadata) {
        console.log('[VIEWER] Metadata too large, fetching from:', data.json_download_url);
        container.innerHTML = '<p class="table-loading-message">Loading table data...</p>';

        try {
            const response = await fetch(data.json_download_url);
            if (!response.ok) {
                throw new Error(`Failed to fetch metadata: ${response.status}`);
            }
            data.table_metadata = await response.json();
            console.log('[VIEWER] Successfully fetched large metadata from S3');
        } catch (error) {
            console.error('[VIEWER] Error fetching metadata:', error);
            container.innerHTML = `<p class="table-empty-message">Error loading table data: ${error.message}</p>`;
            // Still show download buttons even if table fails to load
            _renderViewerButtons(cardId, data);
            return;
        }
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

    // Render download and action buttons
    _renderViewerButtons(cardId, data);
}

/**
 * Helper function to render viewer buttons
 * Extracted to allow reuse in error scenarios
 */
function _renderViewerButtons(cardId, data) {
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
            text: 'Share Table',
            icon: '🔗',
            variant: 'quaternary',
            callback: async (e) => {
                const button = e.target.closest('button');
                await handleShareTable(cardId, button, data);
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
            headers: getAuthHeaders(),
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
    // Add viewer-mode class for wider container
    document.body.classList.add('viewer-mode');

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
            headers: getAuthHeaders(),
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

        // Update card title and subtitle with actual data
        const card = document.getElementById(cardId);
        if (card) {
            const titleEl = card.querySelector('.card-title');
            if (titleEl) {
                titleEl.textContent = data.clean_table_name || tableName;
            }

            // Build subtitle with date info
            const subtitleEl = card.querySelector('.card-subtitle');
            if (subtitleEl) {
                let subtitleParts = [];
                // Use analysis_date if available, otherwise shared_at
                const dateStr = data.analysis_date || data.shared_at;
                if (dateStr) {
                    const dateObj = new Date(dateStr);
                    const formattedDate = dateObj.toLocaleDateString('en-US', {
                        year: 'numeric', month: 'short', day: 'numeric'
                    });
                    subtitleParts.push(data.analysis_date ? `Analyzed: ${formattedDate}` : `Shared: ${formattedDate}`);
                }
                subtitleParts.push('Publicly Shared');
                subtitleEl.textContent = subtitleParts.join(' • ');
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

    // Update the info header with table name and date
    const infoText = document.getElementById(`${cardId}-info-text`);
    if (infoText) {
        const displayName = data.clean_table_name || tableName || 'Shared Table';
        let infoHtml = `<strong>${displayName}</strong>`;

        // Add date context if available
        const dateStr = data.analysis_date || data.shared_at;
        if (dateStr) {
            const dateObj = new Date(dateStr);
            const formattedDate = dateObj.toLocaleDateString('en-US', {
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
            });
            infoHtml += ` - ${data.analysis_date ? 'Validated' : 'Shared'} ${formattedDate}`;
        }

        infoHtml += '. Click cells for details, or download Excel/JSON.';
        infoText.innerHTML = infoHtml;
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

    // Detect reference check table by checking first 2 column names
    const columns = data.table_metadata?.columns || [];
    const colNames = columns.slice(0, 2).map(c => (c.name || '').toLowerCase().trim());
    const isReferenceCheckDemo = colNames.includes('claim id') && colNames.includes('claim order');

    // Build buttons - Create Your Own requires email
    const excelUrl = data.enhanced_download_url || data.download_url;
    const buttons = [];

    if (excelUrl) {
        buttons.push({
            text: 'Download Excel (for Humans)',
            icon: '📥',
            variant: 'secondary',
            callback: (e) => {
                const button = e.target.closest('button');
                markButtonSelected(button, '📥 Downloaded!');
                window.location.href = excelUrl;
                setTimeout(() => markButtonUnselected(button), 2000);
            }
        });
    }

    buttons.push({
        text: 'Download JSON (for AI)',
        icon: '📋',
        variant: 'quaternary',
        callback: (e) => {
            const button = e.target.closest('button');
            downloadJsonMetadata(data.table_metadata, button);
        }
    });

    buttons.push({
        text: isReferenceCheckDemo ? 'Validate New Text' : 'Create Your Own Table',
        icon: isReferenceCheckDemo ? '🔍' : '✨',
        variant: 'primary',
        callback: () => {
            if (isReferenceCheckDemo && typeof createReferenceCheckCard === 'function') {
                // Kick into reference check mode
                requireEmailThen(() => {
                    createReferenceCheckCard();
                }, 'validate text');
            } else if (typeof createUploadOrDemoCard === 'function') {
                createUploadOrDemoCard();
            } else {
                // Fallback: redirect to main app
                window.location.href = window.location.pathname;
            }
        }
    });

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
            headers: getAuthHeaders(),
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

/**
 * Handle the Share Table button click.
 * Checks if already shared, then shows dialog with share/unshare/copy-link options.
 *
 * @param {string} cardId - Card ID for showing messages (can be null for completion card)
 * @param {HTMLElement} button - Button element for state updates
 * @param {Object} data - Results data containing session info
 */
async function handleShareTable(cardId, button, data) {
    const params = getViewerParams();
    const sessionId = params.session || data.session_id || globalState.sessionId;
    const messagesId = cardId ? `${cardId}-messages` : null;

    if (!sessionId) {
        if (messagesId) showMessage(messagesId, 'No session ID available to share.', 'error');
        return;
    }

    // Check current share status first
    markButtonSelected(button, '🔗 Checking...');
    let shareStatus = null;
    try {
        const statusResp = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ action: 'checkShareStatus', session_id: sessionId })
        });
        const statusData = await statusResp.json();
        if (statusData.success) {
            shareStatus = statusData;
        }
    } catch (err) {
        console.warn('[SHARE] Could not check share status:', err);
    }
    markButtonUnselected(button);

    const isCurrentlyShared = shareStatus && shareStatus.is_shared;
    const existingDemoName = isCurrentlyShared ? shareStatus.table_name : null;

    // Show dialog with appropriate options
    const action = await showShareConfirmationDialog(isCurrentlyShared, existingDemoName);
    if (!action) return; // cancelled

    if (action === 'copy') {
        // Copy existing link
        const shareUrl = `https://eliyahu.ai/viewer?demo=${existingDemoName}`;
        try {
            await navigator.clipboard.writeText(shareUrl);
            if (messagesId) showMessage(messagesId,
                `Link copied! <a href="${shareUrl}" target="_blank" style="color: inherit; text-decoration: underline;">${shareUrl}</a>`,
                'success');
        } catch (clipErr) {
            if (messagesId) showMessage(messagesId,
                `Share link: <a href="${shareUrl}" target="_blank" style="color: inherit; text-decoration: underline;">${shareUrl}</a>`,
                'success');
        }
        return;
    }

    if (action === 'unshare') {
        try {
            markButtonSelected(button, '🔗 Removing...');
            const resp = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    action: 'unshareTable',
                    session_id: sessionId,
                    table_name: existingDemoName
                })
            });
            const result = await resp.json();
            if (!resp.ok || !result.success) {
                throw new Error(result.error || 'Failed to unshare');
            }
            if (messagesId) showMessage(messagesId, 'Table is no longer shared publicly.', 'success');
            markButtonSelected(button, '🔗 Unshared');
            setTimeout(() => {
                markButtonUnselected(button);
                const btnText = button.querySelector('.button-text');
                if (btnText) btnText.textContent = '🔗 Share Table';
            }, 2000);
        } catch (error) {
            console.error('[SHARE] Unshare error:', error);
            if (messagesId) showMessage(messagesId, `Unshare failed: ${error.message}`, 'error');
            markButtonUnselected(button);
        }
        return;
    }

    // action === 'share'
    try {
        markButtonSelected(button, '🔗 Sharing...');

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'shareTable',
                session_id: sessionId,
                version: params.version || data.version
            })
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || 'Failed to share table');
        }

        // Build the share URL
        const shareUrl = `https://eliyahu.ai/viewer?demo=${result.table_name}`;

        // Copy to clipboard
        try {
            await navigator.clipboard.writeText(shareUrl);
            if (messagesId) showMessage(messagesId,
                `Share link copied to clipboard! <a href="${shareUrl}" target="_blank" style="color: inherit; text-decoration: underline;">${shareUrl}</a>`,
                'success');
        } catch (clipErr) {
            console.warn('[SHARE] Clipboard write failed:', clipErr);
            if (messagesId) showMessage(messagesId,
                `Share link: <a href="${shareUrl}" target="_blank" style="color: inherit; text-decoration: underline;">${shareUrl}</a> (copy manually)`,
                'success');
        }

        markButtonSelected(button, '🔗 Shared! Link copied');
        setTimeout(() => {
            markButtonUnselected(button);
            const btnText = button.querySelector('.button-text');
            if (btnText) btnText.textContent = '🔗 Share Table';
        }, 3000);

    } catch (error) {
        console.error('[SHARE] Error:', error);
        if (messagesId) showMessage(messagesId, `Share failed: ${error.message}`, 'error');
        markButtonUnselected(button);
    }
}

/**
 * Show share confirmation dialog. If the table is already shared, offers
 * Copy Link, Unshare, and Re-share options. Otherwise shows the standard
 * share warning with Cancel/Share buttons.
 *
 * @param {boolean} isCurrentlyShared - Whether the table is already shared
 * @param {string} existingDemoName - The current demo slug if shared
 * @returns {Promise<string|false>} 'share', 'unshare', 'copy', or false (cancelled)
 */
function showShareConfirmationDialog(isCurrentlyShared, existingDemoName) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'table-maker-modal-overlay';

        let bodyHtml, buttonsHtml;

        if (isCurrentlyShared) {
            const shareUrl = `https://eliyahu.ai/viewer?demo=${existingDemoName}`;
            bodyHtml = `
                <div class="table-maker-modal-header">
                    <h2 class="table-maker-modal-title">Table Already Shared</h2>
                    <p class="table-maker-modal-subtitle">This table has a public share link</p>
                </div>
                <div style="margin-bottom: 1rem;">
                    <div class="message message-info" style="display: flex;">
                        <span class="message-icon">🔗</span>
                        <span style="word-break: break-all;"><a href="${shareUrl}" target="_blank" style="color: inherit;">${shareUrl}</a></span>
                    </div>
                </div>
            `;
            buttonsHtml = `
                <div style="display: flex; gap: 10px; justify-content: flex-end; flex-wrap: wrap;">
                    <button class="std-button secondary" id="share-dialog-cancel" style="min-width: 80px;">
                        <span class="button-text">Cancel</span>
                    </button>
                    <button class="std-button tertiary" id="share-dialog-unshare" style="min-width: 100px;">
                        <span class="button-text">Unshare</span>
                    </button>
                    <button class="std-button primary" id="share-dialog-copy" style="min-width: 120px;">
                        <span class="button-text">Copy Link</span>
                    </button>
                </div>
            `;
        } else {
            bodyHtml = `
                <div class="table-maker-modal-header">
                    <h2 class="table-maker-modal-title">Share Table Publicly</h2>
                    <p class="table-maker-modal-subtitle">This will create a public link to your results</p>
                </div>
                <div style="margin-bottom: 1.5rem;">
                    <div class="message message-warning" style="display: flex;">
                        <span class="message-icon">⚠️</span>
                        <span><strong>Anyone with the link</strong> will be able to view this table without signing in. The shared table includes all validated data and the Excel file.</span>
                    </div>
                </div>
            `;
            buttonsHtml = `
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="std-button secondary" id="share-dialog-cancel" style="min-width: 100px;">
                        <span class="button-text">Cancel</span>
                    </button>
                    <button class="std-button primary" id="share-dialog-confirm" style="min-width: 140px;">
                        <span class="button-text">Share Publicly</span>
                    </button>
                </div>
            `;
        }

        overlay.innerHTML = `
            <div class="table-maker-modal" style="max-width: 480px;">
                <button class="table-maker-modal-close" id="share-dialog-close">&times;</button>
                ${bodyHtml}
                ${buttonsHtml}
            </div>
        `;

        document.body.appendChild(overlay);

        function cleanup(result) {
            overlay.remove();
            document.removeEventListener('keydown', onKeydown);
            resolve(result);
        }

        function onKeydown(e) {
            if (e.key === 'Escape') cleanup(false);
        }

        document.addEventListener('keydown', onKeydown);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cleanup(false);
        });

        document.getElementById('share-dialog-close').addEventListener('click', () => cleanup(false));
        document.getElementById('share-dialog-cancel').addEventListener('click', () => cleanup(false));

        const confirmBtn = document.getElementById('share-dialog-confirm');
        if (confirmBtn) confirmBtn.addEventListener('click', () => cleanup('share'));

        const copyBtn = document.getElementById('share-dialog-copy');
        if (copyBtn) copyBtn.addEventListener('click', () => cleanup('copy'));

        const unshareBtn = document.getElementById('share-dialog-unshare');
        if (unshareBtn) unshareBtn.addEventListener('click', () => cleanup('unshare'));
    });
}
