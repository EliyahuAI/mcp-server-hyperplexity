/* ========================================
 * 11-preview.js - Preview Validation
 *
 * Handles preview generation, WebSocket updates,
 * and preview result downloads.
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */

function createPreviewCard() {
    console.log('[CREATE_PREVIEW] createPreviewCard() called');
    console.log('[CREATE_PREVIEW] activePreviewCard:', globalState.activePreviewCard);

    // Check if a preview card already exists
    if (globalState.activePreviewCard) {
        console.log('[CREATE_PREVIEW] Preview card already exists, returning early');
        return;
    }

    console.log('[CREATE_PREVIEW] No existing preview card, creating new one');

    // Enable leave page warning now that significant work has been done
    window.leaveWarningEnabled = true;

    // Generate the card ID FIRST
    const cardId = generateCardId();
    console.log('[CREATE_PREVIEW] Generated cardId:', cardId);
    globalState.activePreviewCard = cardId;

    // Update workflow state
    globalState.workflowPhase = 'preview';

    // Ensure processingState exists and set preview state
    ensureProcessingState();
    globalState.processingState.previewStartTime = Date.now();
    globalState.processingState.previewCompleted = false;

    const content = `
        <div id="${cardId}-progress"></div>
        <div id="${cardId}-results" style="display: none;">
            <div id="${cardId}-preview-content"></div>
            <div id="${cardId}-cost-estimate" class="cost-estimate" style="display: none;">
                <div class="cost-estimate-header">Estimates for Processing Entire Table</div>
                <div class="cost-estimate-items" id="${cardId}-estimates"></div>
            </div>
        </div>
        <div id="${cardId}-messages"></div>
    `;

    const card = createCard({
        icon: '👁️',
        title: 'Preview Validation',
        subtitle: 'Testing validation with first 3 rows...',
        content,
        id: cardId  // PASS THE ID EXPLICITLY
    });

    // Auto-start preview with the SAME card ID
    startPreview(cardId);

    return card;
}


async function startPreview(cardId) {
    // Track preview conversion
    trackPreviewConversion(globalState.sessionId);

    // Reset completion state for new preview (fixes hang on repeated previews)
    if (typeof resetCompletionState === 'function') {
        resetCompletionState();
    } else {
        validationCompletionHandled = false;
    }

    // Show thinking indicators
    showThinkingInCard(cardId, 'Preparing preview...', true);
    // Start dummy progress animation for preview
    startDummyProgress(cardId, 90000); // 90 seconds estimated for preview
    // Progress routed to card level;

    try {
        // Always use multipart form for preview since backend expects files

        const formData = new FormData();

        // Only append Excel file if not already uploaded
        if (!globalState.excelFileUploaded) {
            formData.append('excel_file', globalState.excelFile);
        } else {
            // Send a dummy file to satisfy backend file requirement
            const dummyFile = new Blob([JSON.stringify({use_stored_files: true})], {
                type: 'application/json'
            });
            formData.append('dummy_file', dummyFile, 'stored_files_marker.json');
        }

        formData.append('email', globalState.email);
        if (globalState.sessionId) {
            formData.append('session_id', globalState.sessionId);
        } else {
            throw new Error('No session ID available. Please upload an Excel file first.');
        }

        const url = `${API_BASE}/validate?async=true&preview_first_row=true&preview_max_rows=3`;

        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok && data.status === 'processing') {
            // Use the actual session_id returned by the backend instead of guessing
            const actualSessionId = data.session_id || `${globalState.sessionId}_preview`;

            // Use unified WebSocket system
            connectToSession(actualSessionId);
            unregisterCardHandler(cardId);
            registerCardHandler(cardId, ['preview', 'preview_progress', 'progress_update'], (wsData, handlerCardId) => {
                handlePreviewWebSocketMessage(wsData, handlerCardId);
            });

            globalState.excelFileUploaded = true;
            if (data.storage_path) {
                globalState.storagePath = data.storage_path;
            }
        } else if (response.ok && data.success) {
            // Handle case where it completed immediately
            globalState.excelFileUploaded = true;
            if (data.preview_data) {
                showPreviewResults(cardId, data.preview_data);
            }
        } else {
            throw new Error(data.error || 'Failed to start preview');
        }
    } catch (error) {
        completeThinkingInCard(cardId, 'Preview failed');
        // Progress routed to card level;
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

// Fixed handlePreviewWebSocketMessage to use card-specific progress
function handlePreviewWebSocketMessage(data, cardId) {

    if (data.status === 'PROCESSING') {
        // Set this card as active for ticker display
        globalState.activeCardId = cardId;
        globalState.currentValidationState = 'preview';

        // Clear confidence scores for fresh running average
        globalState.confidenceScores = [];
        globalState.currentConfidenceScore = null;

        const message = data.verbose_status || 'Processing...';
        // Update both text and progress if we have percent_complete
        if (data.percent_complete !== undefined) {
            updateThinkingProgress(cardId, data.percent_complete, message);
        } else {
            updateThinkingInCard(cardId, message);
        }
        // Progress routed to card level;
    } else if (data.status === 'COMPLETED') {
        // Hide ticker but KEEP messages for full validation
        globalState.currentValidationState = null;
        hideTicker(cardId);
        // DON'T clear messages - keep them for full validation
        if (globalState.activeCardId === cardId) {
            globalState.activeCardId = null;
        }
        // First update to 100% if we have a progress bar
        const indicator = document.getElementById(`${cardId}-thinking`);
        if (indicator && indicator.classList.contains('with-progress')) {
            updateThinkingProgress(cardId, 100, 'Preview complete!');
            setTimeout(() => {
                completeThinkingInCard(cardId, 'Preview complete!');
            }, 500);

            // Wait for shrink animation to complete before showing results
            // 500ms + 300ms (move to 100%) + 600ms (completion) + 1000ms (shrink) = 2400ms
            if (data.preview_data) {
                setTimeout(() => {
                    showPreviewResults(cardId, data.preview_data);
                }, 2400);
            }
        } else {
            completeThinkingInCard(cardId, 'Preview complete!');
            // No progress bar, show results immediately
            if (data.preview_data) {
                showPreviewResults(cardId, data.preview_data);
            }
        }
        // Progress routed to card level;
    } else if (data.status === 'FAILED' || data.status === 'ERROR') {
        completeThinkingInCard(cardId, 'Preview failed');
        // Progress routed to card level;

        const errorMessage = data.error_message || data.verbose_status || 'Preview validation failed';
        showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');
        console.error('Preview failed:', data);
    }
}

// 6. Processing Card
function createProcessingCard() {
    // GUARD: Prevent duplicate processing
    if (globalState.processingInProgress) {
        console.error('[GUARD] ❌ DUPLICATE PROCESSING BLOCKED - already in progress');
        console.trace('[GUARD] Stack trace of duplicate call:');
        return null;
    }
    globalState.processingInProgress = true;

    const cardId = generateCardId();
    const content = `
        <div id="${cardId}-messages"></div>
    `;

    const card = createCard({
        id: cardId,  // Pass explicit ID
        icon: '⚡',
        title: 'Process',
        subtitle: 'Validating your entire table...',
        content
    });

    // Update workflow state
    globalState.workflowPhase = 'validating';

    // Ensure processingState exists and set validation state
    ensureProcessingState();
    globalState.processingState.validationStartTime = Date.now();
    globalState.processingState.validationCompleted = false;

    // Start processing
    startFullProcessing(cardId);

    return card;
}

async function startFullProcessing(cardId) {
    // SECURITY: Get fresh balance before processing to prevent payment bypass
    let currentBalance = globalState.accountBalance || 0;
    const estimatedCost = globalState.estimatedCost || 0;
    const effectiveCost = globalState.effectiveCost ?? estimatedCost; // Use ?? not || so 0 doesn't fall back

    // If balance seems wrong, refresh it
    if (currentBalance === 0 || currentBalance === undefined) {
        try {
            await refreshCurrentBalance();
            currentBalance = globalState.accountBalance || 0;
        } catch (error) {
            console.error('[SECURITY] Could not refresh balance:', error);
        }
    }


    if (currentBalance < effectiveCost) {
        console.warn(`[SECURITY] Payment bypass attempt blocked - insufficient balance (balance: ${currentBalance}, effectiveCost: ${effectiveCost})`);
        completeThinkingInCard(cardId, 'Insufficient Balance');

        // Mark that user attempted processing
        globalState.userAttemptedProcessing = true;
        globalState.pendingProcessingTrigger = () => {

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

        // Reset any buttons that might be in "Processing..." state
        setTimeout(() => {
            const processingButtons = document.querySelectorAll('button .button-text');
            processingButtons.forEach(buttonText => {
                if (buttonText.textContent.includes('Processing...')) {
                    // Find what the button text should be based on balance
                    const sufficientBalance = currentBalance >= effectiveCost;
                    if (sufficientBalance) {
                        buttonText.textContent = `✨ Process Table${effectiveCost ? ` ($${effectiveCost.toFixed(2)})` : ''}`;
                    } else {
                        const creditsNeeded = Math.max(0, effectiveCost - currentBalance);
                        const recommendedAmount = Math.ceil(creditsNeeded);
                        buttonText.textContent = `💳 Add Credits ($${recommendedAmount.toFixed(2)})`;
                    }
                    buttonText.closest('button').disabled = false;
                }
            });
        }, 100);

        showInsufficientBalanceError({
            current_balance: currentBalance,
            estimated_minimum_cost: effectiveCost
        }, cardId);
        return;
    }

    // Track full validation conversion (balance check passed)
    trackFullValidationConversion(globalState.sessionId, effectiveCost);

    // Show thinking indicators with contextual message
    showThinkingInCard(cardId, 'Initializing validation process...', true);
    // Start dummy progress animation
    startDummyProgress(cardId, 90000); // 90 seconds estimated
    // Progress routed to card level;

    try {

        // Always use multipart form for full processing
        const formData = new FormData();

        // Only append Excel file if not already uploaded
        if (!globalState.excelFileUploaded) {
            formData.append('excel_file', globalState.excelFile);
        } else {
            // Send a dummy config file to satisfy backend file requirement
            const dummyConfig = new Blob([JSON.stringify({use_stored_files: true})], {
                type: 'application/json'
            });
            formData.append('config_file', dummyConfig, 'stored_files_marker.json');
        }

        formData.append('email', globalState.email);
        if (globalState.sessionId) {
            formData.append('session_id', globalState.sessionId);
        } else {
            throw new Error('No session ID available. Please upload an Excel file first.');
        }

        const url = `${API_BASE}/validate?async=true`;

        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok && data.status === 'processing') {
            globalState.excelFileUploaded = true;
            const wsSessionId = data.session_id || globalState.sessionId;

            // Connect to session and register processing handler
            connectToSession(wsSessionId);

            // Unregister any preview handlers to prevent conflicts
            cardHandlers.forEach((handlerInfo, existingCardId) => {
                if (handlerInfo.messageTypes.includes('preview')) {
                    unregisterCardHandler(existingCardId);
                }
            });

            unregisterCardHandler(cardId);
            registerCardHandler(cardId, ['processing'], (wsData, cardId) => {
                handleProcessingWebSocketMessage(wsData, cardId);
            });
        } else {
            throw new Error(data.error || 'Failed to start processing');
        }
    } catch (error) {
        console.error('Full processing error:', error);
        completeThinkingInCard(cardId, 'Processing failed');
        // Progress routed to card level;
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
        // Reset guard flag on error
        globalState.processingInProgress = false;
    }
}
