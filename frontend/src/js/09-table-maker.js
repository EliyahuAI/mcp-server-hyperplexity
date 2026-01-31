/* ========================================
 * 09-table-maker.js - Table Maker Conversation Flow
 *
 * Handles table maker conversation, execution updates,
 * row discovery, and table generation.
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */

// Table Maker state management
const tableMakerState = {
    cardId: null,
    conversationId: null,
    messages: [],
    confirmationResponse: null,
    preInitialized: false,      // Track if warmup/session init has been done
    warmupPromise: null         // Track ongoing warmup request
};

// ============================================
// EARLY INITIALIZATION / WARMUP
// ============================================

/**
 * Pre-initialize table maker session: warm up lambda, get session from backend, connect WebSocket.
 * Call this when user selects "Create Table from Prompt" to reduce latency on first submit.
 *
 * Uses the dedicated initTableMakerSession endpoint which:
 * 1. Goes through the same routing as startTableConversation (proper warmup)
 * 2. Imports and initializes table maker modules
 * 3. Returns a session ID from the backend (authoritative source)
 */
async function preInitializeTableMaker() {
    // Skip if already initialized
    if (tableMakerState.preInitialized) {
        console.log('[TABLE_MAKER] Already pre-initialized, skipping');
        return;
    }

    console.log('[TABLE_MAKER] Pre-initializing: warmup + session + WebSocket');

    // Use initTableMakerSession endpoint - this warms up the actual table maker code path
    // (not just /health which may hit different code). This fires immediately (don't await
    // in main flow) but we store the promise so awaitWarmup() can wait for it.
    const warmupPromise = fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'initTableMakerSession',
            email: globalState.email || ''
            // Don't pass session_id - let backend generate fresh one
        })
    })
    .then(async resp => {
        if (!resp.ok) {
            console.warn('[TABLE_MAKER] Init endpoint returned:', resp.status);
            return null;
        }
        const data = await resp.json();
        if (data.success && data.session_id) {
            // Store session ID from backend (authoritative source)
            globalState.sessionId = data.session_id;
            localStorage.setItem('sessionId', data.session_id);
            console.log('[TABLE_MAKER] Session initialized from backend:', data.session_id);

            // Connect WebSocket now that we have a confirmed session
            if (typeof connectToSession === 'function') {
                console.log('[TABLE_MAKER] Pre-connecting WebSocket for session:', data.session_id);
                connectToSession(data.session_id);
            }
            return data;
        }
        return null;
    })
    .catch(err => {
        // Non-fatal - startTableConversation will get session from backend if this fails
        console.warn('[TABLE_MAKER] Lambda warmup failed (non-fatal):', err.message);
        return null;
    });

    tableMakerState.warmupPromise = warmupPromise;
    tableMakerState.preInitialized = true;
}

/**
 * Wait for warmup to complete (call before first API request)
 */
async function awaitWarmup() {
    if (tableMakerState.warmupPromise) {
        await tableMakerState.warmupPromise;
        tableMakerState.warmupPromise = null;
    }
}

// Reset table maker state - call when starting a new conversation
// NOTE: Does NOT reset preInitialized/warmupPromise - those track Lambda warmup
// which should persist across conversation resets within the same user session
function resetTableMakerState() {
    console.log('[TABLE_MAKER] Resetting state for new conversation');
    tableMakerState.cardId = null;
    tableMakerState.conversationId = null;
    tableMakerState.messages = [];
    tableMakerState.confirmationResponse = null;
    tableMakerState.previewData = null;
    tableMakerState.previewCardId = null;
    tableMakerState.table_name = null;
    tableMakerState.reasoning = null;
    tableMakerState.clarifying_questions = null;
    // NOTE: Do NOT reset preInitialized/warmupPromise here!
    // Those track Lambda warmup state which persists across conversations.
    // They are only reset when the user explicitly starts a fresh table maker flow.
}

function handleTableExecutionUpdate(message) {
    const conversationId = message.conversation_id;
    const phase = message.phase;
    const currentStep = message.current_step;
    const progressPercent = message.progress_percent;
    const status = message.status;

    // CRITICAL: Check phase field
    // If phase='interview', these are dummy messages - show progress but don't trigger actions
    // If phase='execution', these are real - trigger UI changes
    const isRealExecution = (phase === 'execution');

    // Always update progress bar (for both interview and execution phases)
    if (progressPercent !== undefined && status) {
        // Find the most recent card to update progress
        if (cardHandlers.size > 0) {
            const latestCardId = Array.from(cardHandlers.keys()).pop();
            const progressText = document.querySelector(`#${latestCardId} .progress-text`);
            const progressTrack = document.querySelector(`#${latestCardId} .progress-track`);
            const progressSquare = document.querySelector(`#${latestCardId} .progress-square`);

            if (progressText) {
                progressText.textContent = status;
            }

            // Find the wrapper and move it (not the square directly)
            const progressWrapper = document.querySelector(`#${latestCardId} .progress-square-wrapper`);
            if (progressWrapper && progressTrack) {
                const trackWidth = progressTrack.offsetWidth || 120; // default to 120px if not measured
                const wrapperWidth = 37.5; // wrapper is 37.5px wide
                const wrapperOffset = wrapperWidth / 2; // offset to center it
                const position = (progressPercent / 100) * trackWidth - wrapperOffset;
                progressWrapper.style.left = `${position}px`;
            }
        }
    }

    // Only trigger UI changes for real execution messages
    if (!isRealExecution) {
        return; // Dummy message, just update progress, don't trigger boxes
    }

    // DEBUG: Log execution updates to help debug info boxes
    // Handling table execution update

    // Handle step-specific updates (ONLY for real execution)
    switch(currentStep) {
        case 1:
            // Columns complete - clean up card and show colored boxes
            if (message.columns && message.table_name) {
                // Get the latest card ID
                if (cardHandlers.size > 0) {
                    const latestCardId = Array.from(cardHandlers.keys()).pop();
                    const card = document.getElementById(latestCardId);

                    if (card) {
                        // Preserve the thinking indicator if it exists
                        const thinkingIndicator = document.getElementById(`${latestCardId}-thinking`);

                        // Clear the card-content but keep the container
                        const cardContent = card.querySelector('.card-content');
                        if (cardContent) {
                            // Clear all existing content EXCEPT the thinking indicator
                            const elementsToRemove = [];
                            for (let child of cardContent.children) {
                                if (child.id !== `${latestCardId}-thinking`) {
                                    elementsToRemove.push(child);
                                }
                            }
                            elementsToRemove.forEach(el => el.remove());

                            // Add a container for the progress messages and boxes
                            const progressContainer = document.createElement('div');
                            progressContainer.id = `${latestCardId}-progress-content`;
                            cardContent.appendChild(progressContainer);
                        }

                        // Hide buttons during execution
                        const buttonsContainer = document.getElementById(`${latestCardId}-buttons`);
                        if (buttonsContainer) buttonsContainer.style.display = 'none';
                    }
                }

                // Show requirements box first if available
                if (message.requirements) {
                    showRequirementsBox(conversationId, message.requirements);
                }

                // Show colored boxes
                showColumnsBoxes(conversationId, message.columns);

                // Show prepopulated rows if available (from column definition)
                if (message.prepopulated_rows && message.prepopulated_rows.length > 0) {
                    showPrepopulatedRowsBox(
                        conversationId,
                        message.prepopulated_rows,
                        message.total_prepopulated || message.prepopulated_rows.length
                    );
                }
            }
            break;

        case 2:
            // Rows discovered - show rows box
            // Backend sends discovered_rows during step 2 (row discovery phase)
            if (message.discovered_rows) {
                // Showing discovered rows
                showDiscoveredRowsBox(
                    conversationId,
                    message.discovered_rows,
                    message.total_discovered || message.discovered_rows.length
                );
            }
            break;

        case 4:
            // QC complete - check for insufficient rows scenario first
            if (message.insufficient_rows && message.total_approved < 4) {
                showInsufficientRowsMessage(
                    conversationId,
                    message.insufficient_rows_statement,
                    message.insufficient_rows_recommendations,
                    message.total_approved || 0
                );
            }

            // Still update rows box with what we have
            if (message.approved_rows || message.approved_row_count !== undefined) {
                updateRowsBoxWithApproved(
                    conversationId,
                    message.approved_rows || [],
                    message.total_approved || message.approved_row_count || 0,
                    message.qc_summary,
                    message.total_discovered
                );
            }
            break;
    }
}

function showInsufficientRowsMessage(conversationId, statement, recommendations, approvedCount) {
    if (cardHandlers.size === 0) return;

    const latestCardId = Array.from(cardHandlers.keys()).pop();
    const card = document.getElementById(latestCardId);
    if (!card) return;

    let progressContent = document.getElementById(`${latestCardId}-progress-content`);
    if (!progressContent) {
        progressContent = card.querySelector('.card-content');
    }
    if (!progressContent) return;

    // Build recommendations HTML
    let recsHtml = '';
    if (recommendations && recommendations.length > 0) {
        recsHtml = '<ul style="margin: 0.5em 0; padding-left: 1.5em;">';
        recommendations.forEach(rec => {
            recsHtml += `<li><strong>${rec.issue}:</strong> ${rec.recommendation}</li>`;
        });
        recsHtml += '</ul>';
    }

    // Create insufficient rows message box (warning color - orange/yellow)
    const messageHtml = `
        <div class="message" style="margin: 1rem 0; background-color: #fff3e0; color: #e65100; border: 2px solid #ffb74d;">
            <span class="message-icon">[!]</span>
            <div>
                <strong>Insufficient Results (${approvedCount} rows found)</strong><br><br>
                ${statement}<br><br>
                ${recsHtml ? '<strong>Suggestions for better results:</strong>' + recsHtml : ''}
                <div style="margin-top: 1em;">
                    <button class="std-button secondary" onclick="restartTableMaker('${conversationId}')">
                        <span class="button-text">Start New Table</span>
                    </button>
                </div>
            </div>
        </div>
    `;

    progressContent.innerHTML += messageHtml;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function restartTableMaker(conversationId) {
    // Reset warmup state so we get a fresh session for the new conversation
    tableMakerState.preInitialized = false;
    tableMakerState.warmupPromise = null;
    // Clear the old session so backend generates a new one
    globalState.sessionId = null;
    localStorage.removeItem('sessionId');
    // Pre-initialize for the new conversation (will now actually run since preInitialized is false)
    preInitializeTableMaker();
    // Create a new table maker card to start fresh
    createTableMakerCard();
}

function handleTableExecutionComplete(message) {
    const conversationId = message.conversation_id;

    // Get the table maker card ID
    let tableMakerCardId = null;
    if (cardHandlers.size > 0) {
        tableMakerCardId = Array.from(cardHandlers.keys()).pop();
    }

    if (tableMakerCardId) {
        // Update the progress indicator to show completion (but don't hide it yet)
        updateThinkingProgress(tableMakerCardId, 100, 'Table generation complete!');

        // Update the card to show it's complete
        const card = document.getElementById(tableMakerCardId);
        if (card) {
            const cardSubtitle = card.querySelector('.card-subtitle');
            if (cardSubtitle) {
                cardSubtitle.textContent = `${message.table_name} - ${message.row_count} rows generated`;
            }

            // Add a success message to the card
            const messagesDiv = document.getElementById(`${tableMakerCardId}-messages`);
            if (messagesDiv) {
                const successMsg = document.createElement('div');
                successMsg.className = 'message message-success';
                successMsg.innerHTML = `
                    <span class="message-icon">[SUCCESS]</span>
                    <div>Table generation complete! ${message.row_count} rows ready for validation.</div>
                `;
                messagesDiv.appendChild(successMsg);
            }
        }
    }

    // Store the table data in global state for the preview
    if (message.csv_s3_key) globalState.csvS3Key = message.csv_s3_key;
    if (message.config_s3_key) globalState.configS3Key = message.config_s3_key;
    if (message.table_name) globalState.tableName = message.table_name;
    if (message.row_count) globalState.rowCount = message.row_count;

    // Mark config as ready (similar to after AI configuration)
    globalState.configValidated = true;
    globalState.configStored = true;
    globalState.excelFileUploaded = true;

    // Create preview card immediately
    // Creating preview validation card
    globalState.activePreviewCard = null;
    createPreviewCard();

    // CRITICAL FIX: Only hide the progress indicator AFTER the preview card is created
    // This prevents the indicator from disappearing before the user sees what's next
    // Wait for preview card to be visible (createPreviewCard adds DOM elements immediately)
    setTimeout(() => {
        if (tableMakerCardId) {
            // Complete with a shorter delay since preview is already visible
            completeThinkingInCard(tableMakerCardId, 'Complete!', 800);
        }
    }, 500); // Wait 500ms for preview card to render and become visible
}

function handleTableExecutionRestructure(message) {
    const conversationId = message.conversation_id;
    let tableMakerCardId = null;
    if (cardHandlers.size > 0) {
        tableMakerCardId = Array.from(cardHandlers.keys()).pop();
    }
    if (!tableMakerCardId) return;

    console.log('[RESTRUCTURE] Clearing previous state and showing restructure notice');
    clearTableExecutionState(tableMakerCardId);
    updateThinkingProgress(tableMakerCardId, 0, 'Restructuring table...');

    const card = document.getElementById(tableMakerCardId);
    if (card) {
        const messagesDiv = document.getElementById(`${tableMakerCardId}-messages`);
        if (messagesDiv) {
            const restructureMsg = document.createElement('div');
            restructureMsg.className = 'message message-info';
            restructureMsg.innerHTML = `
                <span class="message-icon">[INFO]</span>
                <div>
                    <strong>Restructuring Table</strong><br>
                    ${message.user_facing_message || 'Adjusting table structure to improve row discovery...'}
                    ${message.restructuring_guidance ? createRestructureDetails(message) : ''}
                </div>
            `;
            messagesDiv.appendChild(restructureMsg);
        }
    }
}

function handleTableExecutionUnrecoverable(message) {
    let tableMakerCardId = null;
    if (cardHandlers.size > 0) {
        tableMakerCardId = Array.from(cardHandlers.keys()).pop();
    }
    if (!tableMakerCardId) return;

    // Guard: If rows have already been discovered, this message is likely stale/invalid
    // This can happen when navigating away and back, receiving out-of-order WebSocket messages
    const hasDiscoveredRows = document.querySelector('.discovered-rows-box');
    if (hasDiscoveredRows) {
        console.log('[UNRECOVERABLE] Ignoring - rows already discovered, message likely stale');
        return;
    }

    // Guard: If config has been generated successfully, don't treat as unrecoverable
    if (globalState.currentConfig || globalState.configStored) {
        console.log('[UNRECOVERABLE] Ignoring - config already generated');
        return;
    }

    console.log('[UNRECOVERABLE] Request is impossible');
    completeThinkingInCard(tableMakerCardId, 'Unable to discover rows');

    const card = document.getElementById(tableMakerCardId);
    if (card) {
        const messagesDiv = document.getElementById(`${tableMakerCardId}-messages`);
        if (messagesDiv) {
            const apologyMsg = document.createElement('div');
            apologyMsg.className = 'message message-error';
            apologyMsg.innerHTML = `
                <span class="message-icon">[NOTICE]</span>
                <div>${message.user_facing_apology || "I wasn't able to find rows for this table."}</div>
            `;
            messagesDiv.appendChild(apologyMsg);
        }
    }

    if (message.show_new_table_card) {
        setTimeout(() => showGetStartedCard(), 1500);
    }
}

function clearTableExecutionState(cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;
    const progressContent = document.getElementById(`${cardId}-progress-content`);
    if (!progressContent) return;
    const infoBoxes = progressContent.querySelectorAll('.info-box');
    infoBoxes.forEach(box => box.remove());
    console.log(`[CLEAR_STATE] Removed ${infoBoxes.length} info boxes`);
}

function createRestructureDetails(message) {
    const guidance = message.restructuring_guidance || {};
    const improvements = message.search_improvements || [];
    const reasoning = message.qc_reasoning || '';
    let html = '<details style="margin-top: 10px; font-size: 14px;"><summary style="cursor: pointer; color: #2196F3;">Show Details</summary><div style="margin-top: 8px; padding-left: 12px; border-left: 3px solid #2196F3;">';
    if (reasoning) html += `<p><strong>Why:</strong> ${reasoning}</p>`;
    if (guidance.column_changes) html += `<p><strong>Column Changes:</strong> ${guidance.column_changes}</p>`;
    if (guidance.requirement_changes) html += `<p><strong>Requirements:</strong> ${guidance.requirement_changes}</p>`;
    if (guidance.search_broadening) html += `<p><strong>Search Broadening:</strong> ${guidance.search_broadening}</p>`;
    if (improvements.length > 0) {
        html += '<p><strong>Lessons Learned:</strong></p><ul style="margin: 4px 0; padding-left: 20px;">';
        improvements.slice(0, 5).forEach(imp => html += `<li>${imp}</li>`);
        html += '</ul>';
    }
    html += '</div></details>';
    return html;
}

function showGetStartedCard() {
    // Guard: Check if there's already a Get Started card visible
    const existingGetStartedCard = document.querySelector('.card-title');
    const hasGetStartedCard = existingGetStartedCard &&
        Array.from(document.querySelectorAll('.card-title')).some(
            title => title.textContent.trim() === 'Get Started'
        );

    if (hasGetStartedCard) {
        console.log('[GET_STARTED] Skipping - Get Started card already exists');
        return;
    }

    // Guard: Check if there's an active table making workflow with progress
    // Don't show Get Started if user has rows discovered or config generated
    const activeProgressContent = document.querySelector('[id$="-progress-content"]');
    const hasDiscoveredRows = document.querySelector('.discovered-rows-box');
    const hasConfigGenerated = globalState.currentConfig || globalState.configStored;

    if (activeProgressContent && (hasDiscoveredRows || hasConfigGenerated)) {
        console.log('[GET_STARTED] Skipping - active workflow with progress exists');
        return;
    }

    console.log('[GET_STARTED] Showing new "Get Started" card (same as after email validation)');
    // Reuse the same Get Started card shown after email validation
    createUploadOrDemoCard();
}

function showRequirementsBox(conversationId, requirements) {
    // Find the most recent card
    if (cardHandlers.size === 0) return;

    const latestCardId = Array.from(cardHandlers.keys()).pop();
    const card = document.getElementById(latestCardId);
    if (!card) return;

    // Find the progress-content container created in step 1
    let progressContent = document.getElementById(`${latestCardId}-progress-content`);
    if (!progressContent) {
        // Fallback: use card-content if progress-content doesn't exist
        progressContent = card.querySelector('.card-content');
    }
    if (!progressContent) return;

    // Helper function to strip citations and format text (using ID columns pattern)
    function formatRequirementsText(text) {
        if (!text || text === '(None)') return '(None)';

        // Strip citations [1], [2], etc.
        let formatted = text.replace(/\[\d+\]/g, '');

        // Split by newlines and filter empty
        const lines = formatted.split('\n').filter(line => line.trim());

        // Format each line with bullet (copy ID columns pattern)
        const formattedLines = lines.map(line => {
            // Remove leading "- " if present
            const content = line.replace(/^- /, '').trim();
            if (!content) return '';

            // Add colored bullet inline (pink for requirements)
            return `<span style="display: inline-block; width: 0.8em; height: 0.8em; background: #880e4f; border-radius: 50%; margin-right: 6px; vertical-align: middle;"></span>${content}`;
        }).filter(item => item);

        // Join with <br> (COPY COLUMNS PATTERN)
        return formattedLines.join('<br>');
    }

    // Format hard requirements
    const hardReqs = formatRequirementsText(requirements.hard);
    const softReqs = formatRequirementsText(requirements.soft);

    // Create requirements box HTML (Quinary color - pink/magenta)
    const requirementsBoxHtml = `
        <div class="message" style="margin-bottom: 1rem; background-color: #fce4ec; color: #880e4f; border: 1px solid #f8bbd0;">
            <span class="message-icon">ℹ️</span>
            <div>
                <strong>Row Requirements</strong><br>
                <strong style="font-weight: 700;">Hard Requirements:</strong><br>
                ${hardReqs}<br>
                <strong>Soft Requirements:</strong><br>
                ${softReqs}
            </div>
        </div>
    `;

    // Add to progress content
    progressContent.innerHTML += requirementsBoxHtml;

    // Scroll card into view
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showColumnsBoxes(conversationId, columns) {
    // Find the most recent card
    if (cardHandlers.size === 0) return;

    const latestCardId = Array.from(cardHandlers.keys()).pop();
    const card = document.getElementById(latestCardId);
    if (!card) return;

    // Find the progress-content container created in step 1
    let progressContent = document.getElementById(`${latestCardId}-progress-content`);
    if (!progressContent) {
        // Fallback: use card-content if progress-content doesn't exist
        progressContent = card.querySelector('.card-content');
    }
    if (!progressContent) return;

    // Separate ID and research columns
    const idColumns = columns.filter(c => c.importance && c.importance.toUpperCase() === 'ID');
    const researchColumns = columns.filter(c => !c.importance || c.importance.toUpperCase() !== 'ID');

    // Create ID columns box HTML (REUSE existing pattern from lines 11097-11110)
    const idListHtml = idColumns.map(col => {
        const name = col.name || col;
        const desc = col.description || col.validation_strategy || '';
        return `<span style="display: inline-block; width: 0.8em; height: 0.8em; background: #007bff; border-radius: 50%; margin-right: 6px; vertical-align: middle;"></span><strong>${name}</strong>${desc ? ': ' + desc : ''}`;
    }).join('<br>');

    const idBoxHtml = `
        <div class="message" style="margin-bottom: 1rem; background-color: #e0f7fa; color: #00838f; border: 1px solid #b2ebf2;">
            <span class="message-icon">ℹ️</span>
            <div><strong>ID Columns</strong> (defines rows):<br>${idListHtml}</div>
        </div>
    `;

    // Create research columns box HTML (REUSE existing pattern from lines 11113-11126)
    const researchListHtml = researchColumns.map(col => {
        const name = col.name || col;
        const desc = col.description || col.validation_strategy || '';
        return `<strong>${name}</strong>${desc ? ': ' + desc : ''}`;
    }).join('<br>');

    const researchBoxHtml = `
        <div class="message" style="margin-bottom: 1rem; background-color: #f3e5f5; color: #6a1b9a; border: 1px solid #ce93d8;">
            <span class="message-icon">ℹ️</span>
            <div><strong>Research Columns</strong> (to be validated):<br>${researchListHtml}</div>
        </div>
    `;

    // Add both boxes to progress content
    progressContent.innerHTML += idBoxHtml + researchBoxHtml;

    // Scroll card into view
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showPrepopulatedRowsBox(conversationId, prepopulatedRows, totalCount) {
    console.log('[DEBUG] showPrepopulatedRowsBox called with:', prepopulatedRows.length, 'rows, total:', totalCount);

    // Find the most recent card
    if (cardHandlers.size === 0) {
        console.log('[DEBUG] No card handlers found');
        return;
    }

    const latestCardId = Array.from(cardHandlers.keys()).pop();
    const card = document.getElementById(latestCardId);
    if (!card) {
        console.log('[DEBUG] Card not found:', latestCardId);
        return;
    }

    // Find the progress-content container created in step 1
    let progressContent = document.getElementById(`${latestCardId}-progress-content`);
    if (!progressContent) {
        console.log('[DEBUG] progress-content not found, using fallback');
        progressContent = card.querySelector('.card-content');
    }
    if (!progressContent) {
        console.log('[DEBUG] No progress content found at all');
        return;
    }

    console.log('[DEBUG] Found progress content, building prepopulated rows box');

    // Build rows list (top 15 rows)
    const rowsToShow = prepopulatedRows.slice(0, 15);
    const rowsListHtml = rowsToShow.map(row => {
        // Build display string from ID values
        const idValues = row.id_values || {};
        const displayParts = Object.entries(idValues)
            .filter(([k, v]) => v)
            .map(([k, v]) => `${k}: ${v}`);

        // No score for prepopulated rows
        return `• ${displayParts.join(', ')}`;
    }).join('<br>');

    // Add "more rows" indicator if needed
    const moreRowsHtml = totalCount > 15
        ? `<br><em>+ ${totalCount - 15} more rows</em>`
        : '';

    // Create prepopulated rows box (cyan/teal color - similar to ID columns)
    const rowsBoxHtml = `
        <div class="message prepopulated-rows-box" data-total-count="${totalCount}" style="margin-bottom: 1rem; background-color: #e0f2f1; color: #00695c; border: 1px solid #80cbc4;">
            <span class="message-icon">📋</span>
            <div class="prepopulated-rows-content">
                <strong>Prepopulated Rows: <span class="row-count-text">${totalCount} total</span></strong> (from research)<br>
                ${rowsListHtml}${moreRowsHtml}
            </div>
        </div>
    `;
    progressContent.innerHTML += rowsBoxHtml;

    // Scroll card into view
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showDiscoveredRowsBox(conversationId, discoveredRows, totalCount) {
    console.log('[DEBUG] showDiscoveredRowsBox called with:', discoveredRows.length, 'rows, total:', totalCount);

    // Find the most recent card
    if (cardHandlers.size === 0) {
        console.log('[DEBUG] No card handlers found');
        return;
    }

    const latestCardId = Array.from(cardHandlers.keys()).pop();
    const card = document.getElementById(latestCardId);
    if (!card) {
        console.log('[DEBUG] Card not found:', latestCardId);
        return;
    }

    // Find the progress-content container created in step 1
    let progressContent = document.getElementById(`${latestCardId}-progress-content`);
    if (!progressContent) {
        console.log('[DEBUG] progress-content not found, using fallback');
        // Fallback: use card-content if progress-content doesn't exist
        progressContent = card.querySelector('.card-content');
    }
    if (!progressContent) {
        console.log('[DEBUG] No progress content found at all');
        return;
    }

    console.log('[DEBUG] Found progress content, building/updating rows box');

    // Check if rows box already exists (for incremental updates)
    let existingRowsBox = card.querySelector('.discovered-rows-box');

    // Build rows list (top 10-15 rows)
    const rowsToShow = discoveredRows.slice(0, 15);
    const rowsListHtml = rowsToShow.map(row => {
        // Build display string from ID values
        const idValues = row.id_values || {};
        const displayParts = Object.entries(idValues)
            .filter(([k, v]) => v)
            .map(([k, v]) => `${k}: ${v}`);

        // Add row score if available
        const scoreText = row.row_score !== undefined
            ? ` (score: ${row.row_score})`
            : '';

        return `• ${displayParts.join(', ')}${scoreText}`;
    }).join('<br>');

    // Add "more rows" indicator if needed
    const moreRowsHtml = totalCount > 15
        ? `<br><em>+ ${totalCount - 15} more rows</em>`
        : '';

    if (existingRowsBox) {
        // UPDATE existing box (for real-time updates)
        console.log('[DEBUG] Updating existing rows box');
        existingRowsBox.setAttribute('data-total-count', totalCount);
        const rowCountText = existingRowsBox.querySelector('.row-count-text');
        if (rowCountText) {
            rowCountText.textContent = `${totalCount} total`;
        }
        const rowsContent = existingRowsBox.querySelector('.discovered-rows-content');
        if (rowsContent) {
            rowsContent.innerHTML = `<strong>Discovered Rows: <span class="row-count-text">${totalCount} total</span></strong><br>` +
                rowsListHtml + moreRowsHtml;
        }
    } else {
        // CREATE new box (first time)
        console.log('[DEBUG] Creating new rows box');
        const rowsBoxHtml = `
            <div class="message discovered-rows-box" data-total-count="${totalCount}" style="margin-bottom: 1rem; background-color: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7;">
                <span class="message-icon">ℹ️</span>
                <div class="discovered-rows-content">
                    <strong>Discovered Rows: <span class="row-count-text">${totalCount} total</span></strong><br>
                    ${rowsListHtml}${moreRowsHtml}
                </div>
            </div>
        `;
        progressContent.innerHTML += rowsBoxHtml;
    }

    // Scroll card into view (only on first creation, not updates)
    if (!existingRowsBox) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function showClaimsInfoBox(cardId, claims, totalCount = null) {
    const card = document.getElementById(cardId);
    if (!card) return;

    // Use provided totalCount or fall back to claims.length
    const total = totalCount || claims.length;

    const claimsToShow = claims.slice(0, 10);
    const claimsListHtml = claimsToShow.map((claim, index) => {
        // Extract just reference numbers (e.g., [1][2][3] → "1,2,3")
        const refs = claim.reference || 'None';
        let refNumbers = 'None';
        if (refs !== 'None') {
            const matches = refs.match(/\[(\d+)\]/g);
            if (matches) {
                refNumbers = matches.map(m => m.replace(/[\[\]]/g, '')).join(',');
            }
        }

        // Simple number instead of claim_001
        const claimNum = index + 1;
        const statementPreview = claim.statement.length > 100
            ? claim.statement.substring(0, 100) + '...'
            : claim.statement;
        return `<strong>${claimNum}.</strong> ${statementPreview} <span style="color: #666;">[${refNumbers}]</span>`;
    }).join('<br>');

    const moreText = total > 10 ? `<br><em>+${total - 10} more claims</em>` : '';
    const countText = total > 10 ? ` (first ${claimsToShow.length} of ${total})` : '';

    const boxHtml = `
        <div class="message claims-info-box" style="margin-bottom: 1rem; background-color: #fff3e0; color: #e65100; border: 1px solid #ffb74d;">
            <span class="message-icon">📝</span>
            <div><strong>Extracted Claims</strong>${countText}:<br>${claimsListHtml}${moreText}</div>
        </div>
    `;

    // Find form element and insert before success div
    const formEl = document.getElementById(`${cardId}-form`);
    const successEl = document.getElementById(`${cardId}-success`);
    if (formEl && successEl) {
        successEl.insertAdjacentHTML('beforebegin', boxHtml);
    } else if (formEl) {
        formEl.insertAdjacentHTML('afterend', boxHtml);
    }
}

function updateRowsBoxWithApproved(conversationId, approvedRows, totalApproved, qcSummary, totalDiscovered) {
    // Find the discovered rows box in the most recent card
    if (cardHandlers.size === 0) return;

    const latestCardId = Array.from(cardHandlers.keys()).pop();
    const card = document.getElementById(latestCardId);
    if (!card) return;

    // Find the existing rows box
    const rowsBox = card.querySelector('.discovered-rows-box');
    if (!rowsBox) return;

    // Get total discovered from data attribute if not provided
    if (!totalDiscovered) {
        totalDiscovered = parseInt(rowsBox.getAttribute('data-total-count')) || 0;
    }

    // Build approved rows list (top 10-15 rows)
    const rowsToShow = approvedRows.slice(0, 15);
    let rowsListHtml = '';

    if (rowsToShow.length > 0) {
        rowsListHtml = rowsToShow.map(row => {
            // Build display string from ID values
            const idValues = row.id_values || {};
            const displayParts = Object.entries(idValues)
                .filter(([k, v]) => v)
                .map(([k, v]) => `${k}: ${v}`);

            // Add row score if available
            const scoreText = row.row_score !== undefined
                ? ` (score: ${row.row_score})`
                : '';

            return `• ${displayParts.join(', ')}${scoreText}`;
        }).join('<br>');
    }

    // Add "more rows" indicator if needed
    const moreRowsHtml = totalApproved > 15
        ? `<br><em>+ ${totalApproved - 15} more rows</em>`
        : '';

    // Build QC summary if available
    let qcSummaryHtml = '';
    if (qcSummary) {
        const promoted = qcSummary.promoted || 0;
        const demoted = qcSummary.demoted || 0;
        const rejected = qcSummary.rejected || 0;
        qcSummaryHtml = `<br><em>QC Review: +${promoted} promoted, ~${demoted} demoted, -${rejected} rejected</em>`;
    }

    // Update the content of the rows box
    const contentDiv = rowsBox.querySelector('.discovered-rows-content');
    if (contentDiv) {
        contentDiv.innerHTML = `
            <strong>Approved Rows: <span class="row-count-text">${totalApproved} of ${totalDiscovered} discovered</span></strong>${qcSummaryHtml}<br>
            ${rowsListHtml}${moreRowsHtml}
        `;
    }

    // Update data attribute
    rowsBox.setAttribute('data-approved-count', totalApproved);

    // Scroll card into view
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function collapseConversation(conversationId) {
    // Collapse conversation UI - implementation removed
}

function createTableMakerCard() {
// Reset state from any previous conversation to prevent stale data issues
resetTableMakerState();

const cardId = generateCardId();
tableMakerState.cardId = cardId;

const initialPrompt = `<div class="chat-message ai">
    <p>Tell me about your research table!</p>
</div>`;

const content = `
    ${initialPrompt}
    <div id="${cardId}-messages"></div>
    <div id="${cardId}-chat" style="margin-bottom: 16px;"></div>
    <div id="${cardId}-input-container">
        <textarea id="${cardId}-input" class="table-maker-textarea"
            placeholder="Example: Track AI research papers on transformers. Each row is a paper (defined by title and authors). I want columns for citation count, publication venue, key findings, and code availability. This is for my literature review."
            style="width: 100%; min-height: 100px; resize: vertical;"
            onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();const btn=document.querySelector('#${cardId}-buttons button.primary');if(btn){btn.focus();btn.classList.add('hover');setTimeout(()=>btn.classList.remove('hover'),1500);}}"></textarea>
    </div>
`;

const card = createCard({
    id: cardId,
    icon: '🔬',
    title: 'Table Maker',
    subtitle: 'Build a research table through conversation',
    content,
    buttons: [
        {
            text: 'Submit',
            variant: 'primary',
            width: 'full',
            callback: async (e) => {
                const button = e.target.closest('button');
                // Validate input before marking button (so button stays enabled on error)
                const input = document.getElementById(`${cardId}-input`);
                if (!input || !input.value.trim()) {
                    showMessage(`${cardId}-messages`, 'Please describe what table you want to create', 'error');
                    return;
                }
                markButtonSelected(button, 'Thinking...');
                await startTableConversationFromCard(cardId);
            }
        }
    ]
});

return card;
        }

        // Register WebSocket handler for table conversation updates
        function registerTableMakerWebSocketHandler(cardId) {
const card = document.getElementById(cardId);
if (!card) return;

// Register handler with the card ID
registerCardHandler(cardId, ['table_conversation_update'], (data) => {
    // Table maker WebSocket update
    handleTableConversationUpdate(data, cardId);
});
        }

        // Start table conversation from card
        async function startTableConversationFromCard(cardId) {
const input = document.getElementById(`${cardId}-input`);
const userMessage = input.value.trim();

if (!userMessage) {
    showMessage(`${cardId}-messages`, 'Please describe what table you want to create', 'error');
    return;
}

// Hide input container but keep buttons to show "Thinking..." state
const inputContainer = document.getElementById(`${cardId}-input-container`);
if (inputContainer) inputContainer.style.display = 'none';

// Keep buttons visible to show "Thinking..." state
showThinkingInCard(cardId, 'Starting conversation with AI...', true);

// Clear any old table maker state to prevent stale data
// This ensures fresh conversation even if old state lingered
if (tableMakerState.conversationId && tableMakerState.cardId !== cardId) {
    console.log('[TABLE_MAKER] Clearing stale conversation state from previous card');
    resetTableMakerState();
    tableMakerState.cardId = cardId;
}

// Add user message to chat
addChatMessage(cardId, 'user', userMessage);
tableMakerState.messages.push({ role: 'user', content: userMessage });

// Unregister any old table maker handlers before registering new one
// This prevents duplicate message handling from old cards
if (typeof unregisterCardHandler === 'function') {
    // Unregister handlers from cards that no longer exist in DOM
    cardHandlers.forEach((_, existingCardId) => {
        if (existingCardId !== cardId && !document.getElementById(existingCardId)) {
            console.log(`[TABLE_MAKER] Cleaning up orphaned handler for ${existingCardId}`);
            unregisterCardHandler(existingCardId);
        }
    });
}

// Register WebSocket handler
registerTableMakerWebSocketHandler(cardId);

// Update card subtitle
const card = document.getElementById(cardId);
const subtitle = card.querySelector('.card-subtitle');
if (subtitle) {
    subtitle.textContent = 'AI is analyzing your request...';
}

// Send to backend - this will queue the work and return immediately
try {
    // Wait for warmup to complete before making the request
    // This ensures the Lambda is warm and reduces chance of 504 timeout
    if (typeof awaitWarmup === 'function') {
        await awaitWarmup();
    }

    // Use session ID from warmup, or let backend generate one
    // After warmup, globalState.sessionId should be set from initTableMakerSession
    let sessionIdToUse = globalState.sessionId;

    // If we have a session but WebSocket isn't connected, clear it and let backend generate fresh
    if (sessionIdToUse && typeof sessionWebSockets !== 'undefined') {
        const existingWs = sessionWebSockets.get(sessionIdToUse);
        if (!existingWs || existingWs.readyState !== WebSocket.OPEN) {
            console.log('[TABLE_MAKER] No active WebSocket for session, letting backend generate new one');
            sessionIdToUse = null;
        }
    }

    // Send request - backend will generate session_id if not provided
    const response = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'startTableConversation',
            email: globalState.email,
            session_id: sessionIdToUse,  // Backend generates if null
            user_message: userMessage
        })
    });

    const data = await response.json();

    if (data.success && data.status === 'processing') {
        // Request queued successfully - save conversation ID and session ID
        tableMakerState.conversationId = data.conversation_id;

        // Store session_id from backend (always use backend's authoritative value)
        if (data.session_id) {
            globalState.sessionId = data.session_id;
            localStorage.setItem('sessionId', data.session_id);
            // Stored session ID
        }

        // Connect to WebSocket session
        connectToSession(globalState.sessionId);

        // Conversation started
    } else {
        completeThinkingInCard(cardId, 'Failed to start');
        showMessage(`${cardId}-messages`,
            'Failed to start conversation: ' + (data.error || data.message || 'Unknown error'),
            'error');
        document.getElementById(`${cardId}-input-container`).style.display = 'block';
    }
} catch (error) {
    console.error('Error starting table conversation:', error);
    completeThinkingInCard(cardId, 'Error');
    showMessage(`${cardId}-messages`,
        'Failed to start conversation. Please try again.',
        'error');
    document.getElementById(`${cardId}-input-container`).style.display = 'block';
}
        }

        // Handle table conversation updates from WebSocket
        function handleTableConversationUpdate(data, cardId) {
// Processing table maker update

// Update progress if available
if (data.progress !== undefined) {
    if (data.progress < 100) {
        updateThinkingProgress(cardId, data.progress, data.status);
    }
}

// Add AI message when complete
const aiMessage = data.ai_message;
const isReady = data.trigger_execution || data.ready_to_generate || data.trigger_preview;
const showStructure = data.show_structure || false;
const isGenerating = data.is_generating;
const previewGenerated = data.preview_generated;

if (data.progress === 100 && aiMessage && !isGenerating && !previewGenerated) {
    tableMakerState.messages.push({ role: 'ai', content: aiMessage });

    // Store confirmation_response if provided (MODE 2 only)
    if (data.confirmation_response) {
        tableMakerState.confirmationResponse = data.confirmation_response;
        // Stored confirmation response
    }

    // Determine which UI to show based on mode
    if (!isReady) {
        // MODE 1 or MODE 2: Complete the indicator properly
        // Completing progress indicator
        completeThinkingInCard(cardId, 'Response received');

        // Add AI message with streaming
        addChatMessage(cardId, 'ai', aiMessage, false, 'normal');

        // Store table name if provided
        if (data.table_name) {
            tableMakerState.table_name = data.table_name;
        }

        // Update subtitle
        const card = document.getElementById(cardId);
        const subtitle = card.querySelector('.card-subtitle');
        if (subtitle) {
            subtitle.textContent = `Turn ${data.turn_count || tableMakerState.messages.length / 2}`;
        }

        // Check if showing structure (columns and rows preview)
        if (showStructure && data.preview_data) {
            console.log('[TABLE_MAKER] Showing proposed table structure');
            // Show proposed table structure in the same card
            showTablePreviewInCard(cardId, data.preview_data, null);
        }

        // Show refinement input with Submit button
        // Showing refinement input
        showRefinementInput(cardId);
    } else if (isReady) {
        // MODE 3: Don't complete the indicator, keep it running for table generation
        // Execution starting
        // Enable leave page warning - interview is done, table generation starting
        window.leaveWarningEnabled = true;
        updateThinkingInCard(cardId, 'Starting table generation...');

        // Add AI message with streaming
        addChatMessage(cardId, 'ai', aiMessage, false, 'normal');

        // Store table name if provided
        if (data.table_name) {
            tableMakerState.table_name = data.table_name;
        }

        // Update subtitle
        const card = document.getElementById(cardId);
        const subtitle = card.querySelector('.card-subtitle');
        if (subtitle) {
            subtitle.textContent = `Turn ${data.turn_count || tableMakerState.messages.length / 2}`;
        }

        // Check if showing structure (columns and rows preview)
        if (showStructure && data.preview_data) {
            console.log('[TABLE_MAKER] Showing proposed table structure');
            // Show proposed table structure in the same card
            showTablePreviewInCard(cardId, data.preview_data, null);
        }
    }
}

// Handle preview generation complete
if (previewGenerated && data.preview_data) {
    console.log('[TABLE_MAKER] Preview generation complete, populating preview card');
    console.log('[TABLE_MAKER] preview_data keys:', Object.keys(data.preview_data));

    // Use the stored preview card ID
    const previewCardId = tableMakerState.previewCardId;
    console.log('[TABLE_MAKER] Using stored preview card ID:', previewCardId);

    if (previewCardId) {
        // Complete the thinking indicator
        completeThinkingInCard(previewCardId, 'Preview generated');

        // Populate the existing preview card with data
        showTablePreviewInCard(previewCardId, data.preview_data, data.download_url);

        // Update card subtitle to table name if provided
        const card = document.getElementById(previewCardId);
        const cardSubtitle = card?.querySelector('.card-subtitle');
        if (cardSubtitle && data.table_name) {
            cardSubtitle.textContent = data.table_name;
        }
    } else {
        // Creating new preview card
        createTablePreviewCard(data.preview_data, data.download_url, data.table_name);
    }
}

// Handle errors
if (data.error) {
    completeThinkingInCard(cardId, 'Error occurred');
    showMessage(`${cardId}-messages`, `Error: ${data.error}`, 'error');
}
        }

        // Show refinement input
        function showRefinementInput(cardId) {
const card = document.getElementById(cardId);
if (!card) return;

const chatContainer = document.getElementById(`${cardId}-chat`);
let buttonsContainer = document.getElementById(`${cardId}-buttons`);

// Add chat bubbles for refinement guidance
if (chatContainer && (tableMakerState.reasoning || tableMakerState.clarifying_questions)) {
    // First bubble: prompt for changes with better language
    addChatMessage(cardId, 'ai', '**What do you like about the columns and rows? What can I change?**', false, 'normal');

    // Second bubble: reasoning as context paragraph (if exists)
    if (tableMakerState.reasoning && tableMakerState.reasoning.trim()) {
        const reasoningText = tableMakerState.reasoning.trim();
        addChatMessage(cardId, 'ai', reasoningText, false, 'normal');
    }

    // Third bubble: clarifying questions as markdown list with alternatives
    if (tableMakerState.clarifying_questions && tableMakerState.clarifying_questions.trim()) {
        const questionsText = tableMakerState.clarifying_questions.trim();
        // Format as markdown with "Or would you prefer:" for alternatives
        const formattedQuestions = questionsText
            .split(/\n+/)
            .filter(q => q.trim())
            .map(q => {
                // Remove numbering, bullets, and leading punctuation
                let cleaned = q.trim()
                    .replace(/^[\d]+[\.)]\s*/, '')  // Remove "1. " or "1) "
                    .replace(/^[-*•]\s*/, '')        // Remove "- ", "* ", "• "
                    .replace(/^\.+\s*/, '');         // Remove leading periods
                cleaned = cleaned.trim();
                return `- ${cleaned}${cleaned.endsWith('?') ? '' : '?'}`;
            })
            .join('\n');

        if (formattedQuestions) {
            addChatMessage(cardId, 'ai', `**Here are some things to consider:**\n\n${formattedQuestions}\n\n*Or would you prefer something else?*`, false, 'normal');
        }
    }
}

// Create refinement input if it doesn't exist
let refinementDiv = document.getElementById(`${cardId}-refinement`);
if (!refinementDiv) {
    refinementDiv = document.createElement('div');
    refinementDiv.id = `${cardId}-refinement`;
    refinementDiv.style.cssText = 'margin-top: 16px;';
    refinementDiv.innerHTML = `
        <textarea id="${cardId}-refine-input" class="table-maker-textarea"
            placeholder="Confirm or ask for changes (blank to confirm)..."
            style="width: 100%; min-height: 60px; resize: vertical; margin-bottom: 8px;"
            onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();const btn=document.querySelector('#${cardId}-buttons button.primary');if(btn){btn.focus();btn.classList.add('hover');setTimeout(()=>btn.classList.remove('hover'),1500);}}"></textarea>
    `;

    // Append to card content (not using buttonsContainer.parentNode which may not exist)
    const cardContent = card.querySelector('.card-content');
    if (cardContent) {
        cardContent.appendChild(refinementDiv);
    }
}

// Make sure refinement input is visible (may have been hidden after previous submit)
refinementDiv.style.display = 'block';

// STANDARD PATTERN: Always clear text box when AI requests new input (matches Config flows)
const refineInput = document.getElementById(`${cardId}-refine-input`);
if (refineInput) {
    refineInput.value = '';  // Clear previous message
    refineInput.focus();      // Auto-focus for better UX
}

// Create buttons container if it doesn't exist
if (!buttonsContainer) {
    buttonsContainer = document.createElement('div');
    buttonsContainer.id = `${cardId}-buttons`;
    buttonsContainer.className = 'card-buttons';
    card.appendChild(buttonsContainer);
}

// Update buttons
createButtonRow(`${cardId}-buttons`, [
    {
        text: 'Submit',
        variant: 'primary',
        width: 'full',
        callback: async (e) => {
            const button = e.target.closest('button');
            markButtonSelected(button, 'Thinking...');
            await continueTableConversationFromCard(cardId);
        }
    }
]);

// Make sure buttons container is visible
buttonsContainer.style.display = 'flex';
        }

        // Create a new "Table Preview" card
        function createTablePreviewCard(previewData, downloadUrl, tableName) {
const previewCardId = generateCardId();

const content = `
    <div id="${previewCardId}-preview-container"></div>
    <div id="${previewCardId}-chat" style="margin-top: 16px;"></div>
`;

const card = createCard({
    id: previewCardId,
    icon: '📊',
    title: 'Table Preview',
    subtitle: tableName || (previewData ? 'Review and refine your table structure' : 'Generating preview...'),
    content,
    buttons: []  // Will be added by showTablePreviewInCard
});

// Populate the preview if data is available
if (previewData) {
    showTablePreviewInCard(previewCardId, previewData, downloadUrl);
}

return previewCardId;  // Return the card ID so caller can reference it
        }

        // Show table preview in card
        function showTablePreviewInCard(cardId, previewData, downloadUrl) {
if (!previewData) return;

const previewContainer = document.getElementById(`${cardId}-preview-container`);
const chatContainer = document.getElementById(`${cardId}-chat`);
if (!previewContainer) return;

// Store preview data
tableMakerState.previewData = previewData;

// Extract columns and sample rows
// Structure: {rows: {sample_rows: [], additional_rows: []}, columns: []}
const columns = previewData.columns || [];
const sampleRows = previewData.sample_rows || previewData.sample_rows_transposed || previewData.rows?.sample_rows || [];
const futureIds = previewData.future_ids || previewData.rows?.additional_rows || [];

// Debug logging for additional rows
// Populating table preview

// Separate ID and Research columns
const idColumns = columns.filter(c => c.importance && c.importance.toUpperCase() === 'ID');
const researchColumns = columns.filter(c => !c.importance || c.importance.toUpperCase() !== 'ID');

// Build interactive table using the InteractiveTable module (if available)
let tableHtml = '';
const hasInteractiveTable = typeof InteractiveTable !== 'undefined';

if (sampleRows.length > 0 && columns.length > 0) {
    if (hasInteractiveTable) {
        // Use InteractiveTable module for interactive rendering
        const tableMetadata = InteractiveTable.fromSampleRows(columns, sampleRows, 3);
        tableHtml = InteractiveTable.render(tableMetadata, {
            showGeneralNotes: false,  // No notes for AI preview
            showLegend: false,        // Simpler view
            maxRows: 3
        });
    } else {
        // Fallback to markdown table if InteractiveTable not available
        const rowsToShow = sampleRows.slice(0, 3);
        const transposedRows = columns.map(col => {
            const colName = col.name || col;
            const isId = col.importance && col.importance.toUpperCase() === 'ID';
            const idMarker = isId ? '🔵 ' : '';
            const values = rowsToShow.map(row => {
                const value = row[colName] || '';
                return String(value).substring(0, 50);
            });
            return `| ${idMarker}**${colName}** | ${values.join(' | ')} |`;
        }).join('\n');

        const header = `| Column | ${rowsToShow.map((_, i) => `Row ${i + 1}`).join(' | ')} |`;
        const separator = `| --- | ${rowsToShow.map(() => '---').join(' | ')} |`;
        const markdownTable = `${header}\n${separator}\n${transposedRows}`;
        tableHtml = renderMarkdown(markdownTable);
    }
}

// Step 1: After 800ms pause, show column definitions, intro message, and table
setTimeout(() => {
    // Step 1a: Add info boxes to preview container FIRST
    let infoBoxesHtml = '';

    // ID Columns list (Blue/Cyan - quaternary color)
    if (idColumns.length > 0) {
        const idListHtml = idColumns.map(col => {
            const name = col.name || col;
            const desc = col.description || '';
            return `<span style="display: inline-block; width: 0.8em; height: 0.8em; background: #007bff; border-radius: 50%; margin-right: 6px; vertical-align: middle;"></span><strong>${name}</strong>${desc ? ': ' + desc : ''}`;
        }).join('<br>');

        infoBoxesHtml += `
            <div class="message" style="margin-bottom: 1rem; background-color: #e0f7fa; color: #00838f; border: 1px solid #b2ebf2;">
                <span class="message-icon">ℹ️</span>
                <div><strong>ID Columns</strong> (defines rows):<br>${idListHtml}</div>
            </div>
        `;
    }

    // Research Columns list (Purple - secondary color)
    if (researchColumns.length > 0) {
        const researchListHtml = researchColumns.map(col => {
            const name = col.name || col;
            const desc = col.description || '';
            return `<strong>${name}</strong>${desc ? ': ' + desc : ''}`;
        }).join('<br>');

        infoBoxesHtml += `
            <div class="message" style="margin-bottom: 1rem; background-color: #f3e5f5; color: #6a1b9a; border: 1px solid #ce93d8;">
                <span class="message-icon">ℹ️</span>
                <div><strong>Research Columns</strong> (to be validated):<br>${researchListHtml}</div>
            </div>
        `;
    }

    // Additional rows - ID columns only (Orange - tertiary color)
    if (futureIds && futureIds.length > 0) {
        const futureIdsList = futureIds.slice(0, 5).map(idSet => {
            const idValues = idColumns.map(col => idSet[col.name] || '').join(', ');
            return `• ${idValues}`;
        }).join('<br>');

        infoBoxesHtml += `
            <div class="message" style="margin-bottom: 1rem; background-color: #fff3e0; color: #e65100; border: 1px solid #ffcc80;">
                <span class="message-icon">ℹ️</span>
                <div><strong>Additional rows</strong> (${futureIds.length} more):<br>${futureIdsList}${futureIds.length > 5 ? '<br>...and more' : ''}</div>
            </div>
        `;
    }

    // Step 1b: Display blue info box, then table, then info boxes below
    if (tableHtml) {
        const blueInfoBox = `
            <div class="message message-info" style="margin-bottom: 1rem;">
                <span class="message-icon">ℹ️</span>
                <div>First 3 rows (transposed) of state of the art AI table generation, prior to Hyperplexity validation.</div>
            </div>
        `;
        previewContainer.innerHTML = `${blueInfoBox}<div style="margin: 16px 0;">${tableHtml}</div>${infoBoxesHtml}`;

        // Initialize interactive table event handlers if using InteractiveTable
        if (hasInteractiveTable) {
            InteractiveTable.init();
        }
    }

    // Step 1c: Add next steps explanation in chat
    if (chatContainer) {
        const explanationDiv = document.createElement('div');
        explanationDiv.className = 'chat-message ai';
        explanationDiv.innerHTML = '<strong>Next Steps:</strong><br>• <strong>🔧 Refine Table</strong> - Continue the conversation to adjust rows or columns<br>• <strong>✨ Validate Table</strong> - Preview Hyperplexity validation of the first few rows';
        chatContainer.appendChild(explanationDiv);

        // Scroll to bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // Update buttons
    const buttonsContainer = document.getElementById(`${cardId}-buttons`);
    if (buttonsContainer) {
        buttonsContainer.style.display = 'block';
        createButtonRow(`${cardId}-buttons`, [
            {
                text: '🔧 Refine Table',
                variant: 'secondary',
                callback: () => showRefinementInput(cardId)
            },
            {
                text: '✨ Validate Table',
                variant: 'primary',
                callback: async (e) => {
                    const button = e.target.closest('button');
                    markButtonSelected(button, '✨ Validating Table...');
                    await acceptTableAndValidateFromCard(cardId);
                }
            }
        ]);
    }
}, 800); // 800ms pause before showing table
        }

        // Continue table conversation from card
        async function continueTableConversationFromCard(cardId) {
const input = document.getElementById(`${cardId}-refine-input`);
if (!input) return;

const userMessage = input.value.trim();

// Check if this is a simple confirmation (blank, "yes", "looks good", etc.)
const isSimpleConfirmation = !userMessage ||
    /^(yes|yeah|yep|yup|sure|ok|okay|good|great|perfect|sounds good|looks good|go|go for it|start|proceed)\.?$/i.test(userMessage);

// If it's a simple confirmation AND we have a pre-generated confirmation_response, use it
if (isSimpleConfirmation && tableMakerState.confirmationResponse) {
    // Using pre-generated confirmation response

    // Add user message to chat (show actual message or affirmative)
    const displayMessage = userMessage || '✓ Confirmed';
    addChatMessage(cardId, 'user', displayMessage);
    tableMakerState.messages.push({ role: 'user', content: userMessage || 'Yes, looks good. Please generate this table.' });

    // Hide refinement input but keep buttons to show "Thinking..." state
    const refinementDiv = document.getElementById(`${cardId}-refinement`);
    if (refinementDiv) refinementDiv.style.display = 'none';

    // Show thinking indicator
    showThinkingInCard(cardId, 'Starting table generation...', true);

    // Use pre-generated confirmation response
    const confirmData = tableMakerState.confirmationResponse;

    // Add AI confirmation message with streaming
    addChatMessage(cardId, 'ai', confirmData.ai_message, false, 'normal');
    tableMakerState.messages.push({ role: 'ai', content: confirmData.ai_message });

    // Clear confirmation response (used once)
    tableMakerState.confirmationResponse = null;

    // Simulate the update message that would come from WebSocket
    // This triggers execution flow in handleTableConversationUpdate
    setTimeout(() => {
        handleTableConversationUpdate({
            type: 'table_conversation_update',
            conversation_id: tableMakerState.conversationId,
            progress: 100,
            ai_message: confirmData.ai_message,
            trigger_execution: true,  // This is the key - triggers execution
            show_structure: false,
            context_web_research: confirmData.context_web_research || [],
            processing_steps: confirmData.processing_steps || [],
            table_name: confirmData.table_name || tableMakerState.table_name,
            turn_count: (tableMakerState.messages.filter(m => m.role === 'user').length)
        }, cardId);
    }, 100);

    return;
}

// Otherwise, send to backend for AI processing (user wants changes)
// Log error if blank confirmation is going to backend (stored response should have been used)
if (isSimpleConfirmation) {
    console.error('[TABLE_MAKER] BUG: Blank/simple confirmation going to backend - confirmationResponse was null/missing. This should have been handled locally.');
}

const messageToSend = userMessage || 'Yes, looks good. Please generate this table.';

// Add user message to chat (show actual message or affirmative)
const displayMessage = userMessage || '✓ Confirmed';
addChatMessage(cardId, 'user', displayMessage);
tableMakerState.messages.push({ role: 'user', content: messageToSend });

// Hide refinement input but keep buttons to show "Thinking..." state
const refinementDiv = document.getElementById(`${cardId}-refinement`);
if (refinementDiv) refinementDiv.style.display = 'none';

// Show thinking indicator in card (buttons will remain showing "Thinking...")
showThinkingInCard(cardId, 'Processing your request...', true);

// Validate required state before making request
if (!globalState.sessionId) {
    console.error('[TABLE_MAKER] Cannot continue: globalState.sessionId is not set');
    completeThinkingInCard(cardId, 'Error');
    showMessage(`${cardId}-messages`,
        'Session not available. Please refresh and try again.',
        'error');
    return;
}

if (!tableMakerState.conversationId) {
    console.error('[TABLE_MAKER] Cannot continue: tableMakerState.conversationId is not set');
    completeThinkingInCard(cardId, 'Error');
    showMessage(`${cardId}-messages`,
        'Conversation not started. Please start a new conversation.',
        'error');
    return;
}

// Log the request details for debugging
console.log('[TABLE_MAKER] Continuing conversation:', {
    sessionId: globalState.sessionId,
    conversationId: tableMakerState.conversationId,
    email: globalState.email,
    messageLength: messageToSend.length
});

// Send to backend
try {
    const response = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'continueTableConversation',
            email: globalState.email,
            session_id: globalState.sessionId,
            conversation_id: tableMakerState.conversationId,
            user_message: messageToSend
        })
    });

    const data = await response.json();

    if (data.success && data.status === 'processing') {
        // Request queued - thinking indicator already showing, no button needed
        // Conversation continue queued
    } else {
        completeThinkingInCard(cardId, 'Error');
        showMessage(`${cardId}-messages`,
            'Failed to continue conversation: ' + (data.error || data.message || 'Unknown error'),
            'error');
    }
} catch (error) {
    // Log detailed error information for debugging
    console.error('[TABLE_MAKER] Error continuing conversation:', {
        error: error.message,
        name: error.name,
        sessionId: globalState.sessionId,
        conversationId: tableMakerState.conversationId
    });

    completeThinkingInCard(cardId, 'Error');

    // Provide more specific error message based on error type
    let errorMessage = 'Failed to send message. ';
    if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
        errorMessage += 'Network error - please check your connection or try refreshing the page.';
    } else {
        errorMessage += 'Please try again.';
    }

    showMessage(`${cardId}-messages`, errorMessage, 'error');
}
}

// Trigger table generation after user confirms the structure
async function triggerTableGeneration(cardId) {
// Add final AI message
await addChatMessage(cardId, 'ai', 'Building out rows and validating the first rows. Will be ready for review in 3-4 minutes.', false, 'normal');

// Hide input/button and show progress
const refinementDiv = document.getElementById(`${cardId}-refinement`);
if (refinementDiv) refinementDiv.remove();

const buttonsContainer = document.getElementById(`${cardId}-buttons`);
if (buttonsContainer) buttonsContainer.remove();

showThinkingInCard(cardId, 'Generating columns and rows...', true);

// Send affirmative response to backend - this will trigger execution
try {
    const response = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'continueTableConversation',
            email: globalState.email,
            session_id: globalState.sessionId,
            conversation_id: tableMakerState.conversationId,
            user_message: 'Yes, looks good. Please generate this table.'
        })
    });

    const data = await response.json();

    if (!data.success) {
        completeThinkingInCard(cardId, 'Error');
        showMessage(`${cardId}-messages`,
            `Failed to start table generation: ${data.error || 'Unknown error'}`,
            'error');
    }
    // If successful, execution will start and we'll get WebSocket updates
} catch (error) {
    console.error('Error triggering table generation:', error);
    completeThinkingInCard(cardId, 'Error');
    showMessage(`${cardId}-messages`,
        'Failed to start table generation. Please try again.',
        'error');
}
}

// Accept table and start validation from card
async function acceptTableAndValidateFromCard(cardId) {
if (!tableMakerState.previewData) {
    showMessage(`${cardId}-messages`, 'No table preview available', 'error');
    return;
}

// Complete the preview card
completeThinkingInCard(cardId, 'Table accepted');

// Create new "Configuration Generation" card
const configCardId = generateCardId();
const configCard = createCard({
    id: configCardId,
    icon: '⚙️',
    title: 'Configuring Validation',
    subtitle: tableMakerState.table_name || 'Generating validation configuration...',
    content: '<div id="' + configCardId + '-messages"></div>',
    buttons: []
});

// Show progress indicator for config generation
showThinkingInCard(configCardId, 'Generating validation configuration...', true);

// Register handler BEFORE fetch to catch early progress messages
unregisterCardHandler(configCardId);
let validationAutoTriggered = false;  // Prevent duplicate auto-triggers
registerCardHandler(configCardId, ['table_finalization_progress'], (wsData, handlerCardId) => {
    // Progress updates are handled by global progress routing
    // This handler is just for completion events
    if (wsData.type === 'table_finalization_progress' && wsData.progress === 100 && !validationAutoTriggered) {
        const message = wsData.message || wsData.status || '';

        // Check if this is table/config generation completion
        if (message.includes('Table generation complete')) {
            // Config generation complete
            validationAutoTriggered = true;  // Set flag to prevent duplicates

            // Update global state
            if (wsData.session_id) globalState.sessionId = wsData.session_id;
            if (wsData.table_filename) globalState.excelFileName = wsData.table_filename;
            globalState.excelFileUploaded = true;
            globalState.configLoaded = true;

            // Complete config card
            completeThinkingInCard(handlerCardId, 'Configuration generated');

            // Create Preview Validation card and auto-trigger validation
            setTimeout(() => {
                // Creating preview validation card
                createPreviewCard();  // This will auto-trigger validation
            }, 500);
        }
    }
});

try {
    const response = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'acceptTableAndValidate',
            email: globalState.email,
            session_id: globalState.sessionId,
            conversation_id: tableMakerState.conversationId,
            table_config: tableMakerState.previewData,
            row_count: 20
        })
    });

    const data = await response.json();

    if (data.success && data.status === 'processing') {
        // Async mode - wait for WebSocket updates (handler already registered above)
        // Async processing started

    } else if (data.success) {
        // Synchronous mode (legacy fallback)
        globalState.sessionId = data.session_id || globalState.sessionId;
        globalState.excelFileName = data.table_filename || 'generated_table.xlsx';
        globalState.excelFileUploaded = true;

        completeThinkingInCard(cardId, 'Table generated!');

        showMessage(`${cardId}-messages`,
            'I have completed a first pass generation of your research table, and will now validate the first 3 rows.',
            'success'
        );

        // Wait 800ms then trigger preview validation
        setTimeout(() => {
            triggerPreviewValidation(cardId);
        }, 800);

    } else {
        completeThinkingInCard(cardId, 'Generation failed');
        showMessage(`${cardId}-messages`,
            'Failed to generate table: ' + (data.error || data.message || 'Unknown error'),
            'error');
        // Show buttons again on error
        if (buttonsContainer) buttonsContainer.style.display = 'block';
    }
} catch (error) {
    console.error('Error accepting table:', error);
    completeThinkingInCard(cardId, 'Error');
    showMessage(`${cardId}-messages`,
        'Failed to generate table. Please try again.',
        'error');
    // Show buttons again on error
    if (buttonsContainer) buttonsContainer.style.display = 'block';
}
}

// Open chat interface modal
// Modal functions removed - using card-based interface only

// Helper function to download unvalidated table
async function downloadUnvalidatedTable() {
    try {
        if (!globalState.sessionId || !globalState.email) {
            throw new Error('Session information not available');
        }

        // Request presigned URL for the generated table
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'getTableDownloadUrl',
                email: globalState.email,
                session_id: globalState.sessionId
            })
        });

        const data = await response.json();

        if (data.success && data.download_url) {
            // Create temporary link and trigger download
            const link = document.createElement('a');
            link.href = data.download_url;
            link.download = data.filename || `table_${globalState.sessionId}.xlsx`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } else {
            throw new Error(data.error || 'Failed to get download URL');
        }
    } catch (error) {
        console.error('Error downloading table:', error);
        alert('Failed to download table: ' + error.message);
    }
}
