/* ========================================
 * WebSocket Module
 * WebSocket connection management, message routing, and real-time updates
 *
 * Dependencies: 00-config.js (globalState, API_BASE, WEBSOCKET_API_URL, ENV_CONFIG)
 *               01-utils.js (showMessage)
 *               02-storage.js (getCurrentUserEmail)
 * ======================================== */

// ============================================
// WEBSOCKET MANAGEMENT
// ============================================

// Unified WebSocket system - one connection per session
const sessionWebSockets = new Map(); // sessionId -> WebSocket
const cardHandlers = new Map(); // cardId -> {handler: function, messageTypes: [], registrationOrder: number}
let registrationCounter = 0;

// Fallback polling state - stored globally so we can manage it
let activeFallbackPolling = null; // { sessionId, intervalId, startTime }

// Global timestamp for last WebSocket message - used to determine if fallback polling should kick in
// This is updated whenever ANY WebSocket message is received, regardless of session
let lastGlobalWebSocketMessageTime = null;

// Track if we've already completed to prevent duplicate handling
let validationCompletionHandled = false;
let completionHandledBy = null; // Track which source handled completion (for debugging)

// Track pending visibility check to prevent queued duplicates
let pendingVisibilityCheck = null;

/**
 * Central completion handler - THE ONLY place that should mark completion as handled.
 * This ensures atomic check-and-set regardless of whether completion comes from
 * WebSocket or API polling.
 *
 * @param {string} source - Where the completion was detected ('websocket', 'api_poll', 'visibility_check', etc.)
 * @returns {boolean} - True if this call handled completion, false if already handled
 */
function tryHandleCompletion(source) {
    if (validationCompletionHandled) {
        console.log(`[COMPLETION] Already handled by '${completionHandledBy}', ignoring duplicate from '${source}'`);
        return false;
    }

    // Atomically mark as handled
    validationCompletionHandled = true;
    completionHandledBy = source;
    console.log(`[COMPLETION] Marked as handled by '${source}' at ${new Date().toISOString()}`);

    // Stop fallback polling since completion is being handled
    stopFallbackPolling();

    return true;
}

// ============================================
// STATUS RECOVERY SYSTEM
// ============================================

/**
 * Check validation status via API and handle completion if detected.
 * This is called on WebSocket reconnect and when tab becomes visible.
 * @param {string} sessionId - The session to check
 * @param {boolean} isPreview - Whether this is a preview check
 * @param {string} source - Where this check originated from (for debugging)
 * @returns {Promise<boolean>} - True if validation was found complete
 */
async function checkValidationStatus(sessionId, isPreview = false, source = 'api_poll') {
    if (!sessionId) return false;

    // Early exit if already completed (avoid unnecessary API calls)
    if (validationCompletionHandled && !isPreview) {
        console.log(`[STATUS_CHECK] Already completed (by '${completionHandledBy}'), skipping API call`);
        return true;
    }

    try {
        console.log(`[STATUS_CHECK] Checking status for session ${sessionId} (preview: ${isPreview}, source: ${source})`);

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'checkStatus',
                session_id: sessionId,
                preview_mode: isPreview
            })
        });

        if (!response.ok) {
            console.warn(`[STATUS_CHECK] Status check failed with HTTP ${response.status}`);
            return false;
        }

        const data = await response.json();
        console.log('[STATUS_CHECK] Status response:', data.status || 'unknown');

        // Check for completion - handle both string 'COMPLETED' and case variations
        const status = (data.status || '').toUpperCase();
        if (status === 'COMPLETED') {
            console.log(`[STATUS_CHECK] API reports COMPLETED - routing to handler (source: ${source})`);

            // Ensure processing state exists before routing
            if (typeof ensureProcessingState === 'function') {
                ensureProcessingState();
            }

            if (globalState.processingState) {
                globalState.processingState.validationCompleted = true;
            }
            globalState.workflowPhase = 'completed';

            // Route through routeMessage which handles deduplication via tryHandleCompletion
            // The source is passed through the data so routeMessage knows where it came from
            routeMessage({
                status: 'COMPLETED',
                _completionSource: source,
                ...data
            }, sessionId);

            return true;
        }

        return false;
    } catch (error) {
        console.error(`[STATUS_CHECK] Error checking status:`, error);
        return false;
    }
}

/**
 * Stop the fallback polling if it's active
 */
function stopFallbackPolling() {
    if (activeFallbackPolling) {
        console.log(`[FALLBACK] Stopping polling for session ${activeFallbackPolling.sessionId}`);
        clearInterval(activeFallbackPolling.intervalId);
        activeFallbackPolling = null;
    }
}

/**
 * Reset completion handled flag - call this when starting a new validation.
 * This should be called ONCE when validation transitions to PROCESSING state,
 * not on every PROCESSING message.
 */
function resetCompletionState() {
    validationCompletionHandled = false;
    completionHandledBy = null;
    stopFallbackPolling();

    // Clear any pending visibility check
    if (pendingVisibilityCheck) {
        clearTimeout(pendingVisibilityCheck);
        pendingVisibilityCheck = null;
    }
    console.log('[COMPLETION] State reset for new validation');
}

function connectToSession(sessionId, reconnectAttempt = 0) {
    // Return existing connection if available and truly healthy
    if (sessionWebSockets.has(sessionId)) {
        const existingWs = sessionWebSockets.get(sessionId);
        if (existingWs.readyState === WebSocket.OPEN) {
            return existingWs;
        } else {
            // Clean up old connection
            if (existingWs._healthCheckInterval) {
                clearInterval(existingWs._healthCheckInterval);
            }
            if (existingWs._pingInterval) {
                clearInterval(existingWs._pingInterval);
            }
            try {
                existingWs.close();
            } catch (error) {
                console.error(`Error closing existing WebSocket:`, error);
            }
            sessionWebSockets.delete(sessionId);
        }
    }


    const ws = new WebSocket(WEBSOCKET_API_URL);
    sessionWebSockets.set(sessionId, ws);

    ws.onopen = () => {
        if (ws.readyState === WebSocket.OPEN) {
            try {
                console.log(`[WEBSOCKET] Connection opened for session ${sessionId}${reconnectAttempt > 0 ? ` (reconnect attempt ${reconnectAttempt})` : ''}`);
                ws.send(JSON.stringify({
                    action: 'subscribe',
                    sessionId: sessionId
                }));
                console.log(`[WEBSOCKET] Subscribed to session ${sessionId}`);

                // On reconnection during full validation, immediately check status
                // This catches cases where validation completed while we were disconnected
                if (reconnectAttempt > 0 && globalState.currentValidationState === 'full') {
                    console.log('[WEBSOCKET] Reconnected during full validation - checking status');
                    checkValidationStatus(sessionId, false, 'websocket_reconnect').then(completed => {
                        if (completed) {
                            console.log('[WEBSOCKET] Validation was completed during disconnect - UI updated');
                        }
                    });
                }

                // Track last message time for health monitoring
                ws._lastMessageTime = Date.now();

                // Track ping metrics
                ws._pingsSent = 0;
                ws._pongsReceived = 0;
                ws._lastPingTime = null;

                // Start keepalive ping to prevent idle timeout (AWS API Gateway default is 10 min)
                ws._pingInterval = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        try {
                            ws._pingsSent++;
                            ws._lastPingTime = Date.now();
                            ws.send(JSON.stringify({ action: 'ping' }));
                        } catch (error) {
                            console.error(`[WEBSOCKET] Error sending ping for session ${sessionId}:`, error);
                            clearInterval(ws._pingInterval);
                        }
                    } else {
                        console.warn(`[WEBSOCKET] Ping interval stopped - connection not open (state: ${ws.readyState})`);
                        clearInterval(ws._pingInterval);
                    }
                }, 45000); // Send ping every 45 seconds

                // Start periodic health checks with reconnection
                ws._healthCheckInterval = setInterval(() => {
                    if (ws.readyState !== WebSocket.OPEN && ws.readyState !== WebSocket.CONNECTING) {
                        console.warn(`[WEBSOCKET] Health check failed for session ${sessionId}, readyState: ${ws.readyState}. Triggering reconnection...`);
                        clearInterval(ws._healthCheckInterval);
                        clearInterval(ws._pingInterval);
                        sessionWebSockets.delete(sessionId);

                        // Trigger reconnection
                        if (!ws._intentionallyClosed) {
                            connectToSession(sessionId, 0);
                        }
                    }
                }, 30000); // Check every 30 seconds
            } catch (error) {
                console.error(`Error subscribing to session ${sessionId}:`, error);
            }
        }
    };

    ws.onmessage = (event) => {
        // Track last message time for health checks
        const now = Date.now();
        ws._lastMessageTime = now;

        try {
            // Check if this is a pong response - DON'T update global timestamp for pongs
            // We only want content messages to indicate the WebSocket is delivering data
            if (event.data === 'pong' || event.data === 'Pong' || event.data === '"pong"') {
                ws._pongsReceived++;
                return; // Don't route pong messages
            }

            // Only update global timestamp for actual content messages
            // This ensures fallback polling kicks in if WebSocket isn't delivering content
            lastGlobalWebSocketMessageTime = now;

            const data = JSON.parse(event.data);

            // Validate data is not null/undefined before routing
            if (data && typeof data === 'object') {
                // Process through message queue for deduplication and ordering
                if (typeof processIncomingMessage === 'function') {
                    const { shouldProcess, isOutOfOrder } = processIncomingMessage(data);
                    if (!shouldProcess) {
                        // Message is duplicate or queued for later processing
                        if (!isOutOfOrder) {
                            console.log('[WEBSOCKET] Skipping duplicate message:', data.type);
                        }
                        return;
                    }
                }

                routeMessage(data, sessionId);
            }
        } catch (error) {
            console.error(`Failed to parse WebSocket message for session ${sessionId}:`, error, event.data);
        }
    };

    ws.onerror = (error) => {
        console.error(`WebSocket error for session ${sessionId}:`, error);
    };

    ws.onclose = (event) => {
        sessionWebSockets.delete(sessionId);

        // Clean up all intervals
        if (ws._healthCheckInterval) {
            clearInterval(ws._healthCheckInterval);
        }
        if (ws._pingInterval) {
            clearInterval(ws._pingInterval);
        }

        const isUnexpectedClose = event.code !== 1000 && event.code !== 1001;
        const maxReconnectAttempts = 20;
        const wasIntentionallyClosed = ws._intentionallyClosed;

        if (isUnexpectedClose && reconnectAttempt < maxReconnectAttempts && !wasIntentionallyClosed) {
            // Progressive backoff: 1s, 2s, 4s, 8s, then 15s for remaining attempts
            const reconnectDelay = reconnectAttempt < 4
                ? 1000 * Math.pow(2, reconnectAttempt)
                : 15000;

            // Show warning after 10 failed attempts during full validation
            if (reconnectAttempt === 10 && globalState.currentValidationState === 'full' && globalState.activeCardId) {
                const messageContainer = `${globalState.activeCardId}-messages`;
                showMessage(
                    messageContainer,
                    `<strong>Connection Issues</strong><br>Having trouble maintaining connection. If this continues, your results will be emailed to you.`,
                    'warning',
                    false,
                    'connection-warning'
                );
            }

            setTimeout(() => {
                connectToSession(sessionId, reconnectAttempt + 1);
            }, reconnectDelay);
        } else if (isUnexpectedClose) {
            console.error(`[WEBSOCKET] Max reconnection attempts (${maxReconnectAttempts}) reached for session ${sessionId}`);

            // Special handling for validation disconnections (both full and preview)
            if ((globalState.currentValidationState === 'full' || globalState.currentValidationState === 'preview') && globalState.activeCardId) {
                const messageContainer = `${globalState.activeCardId}-messages`;
                const emailAddress = globalState.currentEmail || 'your registered email';
                const isPreview = globalState.currentValidationState === 'preview';
                const validationType = isPreview ? 'preview' : 'validation';

                // Different messages for preview vs full validation
                const resultInfo = isPreview
                    ? 'Refresh this page to check if preview completed.'
                    : `Results will be emailed to <strong>${emailAddress}</strong> when complete.`;

                showMessage(
                    messageContainer,
                    `<strong>Connection Lost</strong><br><br>
                    Don't worry - your ${validationType} is still running on our servers.<br><br>
                    ${resultInfo}<br><br>
                    If issues persist, please contact <a href="mailto:eliyahu@eliyahu.ai?subject=Validation%20${sessionId}">eliyahu@eliyahu.ai</a> with session ID: <code>${sessionId}</code>`,
                    'warning',
                    false
                );

                // Fallback polling should still be running - it will detect completion
                console.log(`[WEBSOCKET] Fallback polling should handle completion detection for ${validationType}`);
            }
        }
    };

    return ws;
}

function isWebSocketHealthy(ws) {
    if (!ws) return false;
    return ws.readyState === WebSocket.OPEN;
}

function ensureWebSocketHealth(sessionId) {
    // Only create if doesn't exist, don't recreate existing connections
    if (!sessionWebSockets.has(sessionId)) {
        return connectToSession(sessionId);
    }

    const ws = sessionWebSockets.get(sessionId);
    return ws;
}

function setupWebSocketFallback(sessionId, options = {}) {
    // Stop any existing fallback polling first
    stopFallbackPolling();

    const {
        pollInterval = 10000,  // Check every 10 seconds (reduced frequency to be lighter)
        maxDuration = 20 * 60 * 1000,  // 20 minutes max (covers most validations)
        isPreview = false,
        silenceThreshold = 30000  // Only poll if no WebSocket message for 30 seconds
    } = options;

    console.log(`[FALLBACK] Starting polling for session ${sessionId} (preview: ${isPreview}, duration: ${maxDuration / 60000}min, silence threshold: ${silenceThreshold / 1000}s)`);

    const startTime = Date.now();

    // Poll for completion ONLY if WebSocket messages aren't coming through
    const fallbackInterval = setInterval(async () => {
        // Check if validation has already been handled
        if (validationCompletionHandled && !isPreview) {
            console.log('[FALLBACK] Completion already handled, stopping polling');
            stopFallbackPolling();
            return;
        }

        // Check if we're in a stable state (no active validation)
        // Only stop if validation state is explicitly NOT 'full' (for full validation polling)
        // or NOT 'preview' (for preview polling)
        const expectedState = isPreview ? 'preview' : 'full';
        if (globalState.currentValidationState !== expectedState) {
            // Validation finished, failed, or was cancelled - stop polling
            console.log(`[FALLBACK] Validation state changed from '${expectedState}' to '${globalState.currentValidationState}', stopping polling`);
            stopFallbackPolling();
            return;
        }

        // Check max duration
        if (Date.now() - startTime > maxDuration) {
            console.log('[FALLBACK] Max polling duration reached, stopping');
            stopFallbackPolling();
            return;
        }

        // CRITICAL: Only poll if we haven't received a WebSocket message recently
        // This prevents the API poll from interfering with healthy WebSocket connections
        // Uses global timestamp to handle session ID mismatches between WS and polling
        if (lastGlobalWebSocketMessageTime) {
            const timeSinceLastMessage = Date.now() - lastGlobalWebSocketMessageTime;
            if (timeSinceLastMessage < silenceThreshold) {
                // WebSocket is healthy and sending messages, skip this poll cycle
                console.log(`[FALLBACK] WebSocket active (${Math.round(timeSinceLastMessage / 1000)}s ago), skipping poll`);
                return;
            }
            console.log(`[FALLBACK] WebSocket silent for ${Math.round(timeSinceLastMessage / 1000)}s, polling API`);
        } else {
            console.log('[FALLBACK] No WebSocket messages received yet, polling API');
        }

        // Use the centralized status check function with source tracking
        const completed = await checkValidationStatus(sessionId, isPreview, 'fallback_poll');
        if (completed) {
            console.log('[FALLBACK] Validation completed via polling');
            // stopFallbackPolling() is called by tryHandleCompletion, but call again to be safe
            stopFallbackPolling();
        }
    }, pollInterval);

    // Store the polling state
    activeFallbackPolling = {
        sessionId,
        intervalId: fallbackInterval,
        startTime,
        isPreview
    };
}

// ============================================
// CARD HANDLER REGISTRATION
// ============================================

function registerCardHandler(cardId, messageTypes, handler) {
    if (!cardId || typeof handler !== 'function') {
        return;
    }

    // First unregister any existing handler to prevent duplicates
    if (cardHandlers.has(cardId)) {
        cardHandlers.delete(cardId);
    }

    cardHandlers.set(cardId, {
        handler: handler,
        messageTypes: messageTypes || [],
        registrationOrder: ++registrationCounter
    });

    // Check WebSocket health when registering a new handler
    if (globalState.sessionId) {
        ensureWebSocketHealth(globalState.sessionId);
    }
}

function unregisterCardHandler(cardId) {
    if (cardId && cardHandlers.has(cardId)) {
        cardHandlers.delete(cardId);
    }
}

// ============================================
// MESSAGE ROUTING
// ============================================

function routeMessage(data, sessionId) {
    // Safety check: ensure data is valid
    if (!data || typeof data !== 'object') {
        return;
    }

    // Restart inactivity timer if we have an active async process
    if (window.asyncTimeouts && window.asyncTimeouts.has(sessionId)) {
        const timeoutInfo = window.asyncTimeouts.get(sessionId);
        if (timeoutInfo && timeoutInfo.restartInactivityTimer) {
            const hasActiveProgress = data.progress !== undefined &&
                                      data.progress > 0 &&
                                      data.progress < 100;

            const isProgressMessage = data.type === 'progress' ||
                                      data.type === 'progress_update' ||
                                      data.type === 'status_update';

            if (hasActiveProgress || isProgressMessage) {
                timeoutInfo.restartInactivityTimer();
                timeoutInfo.activeProcessing = true;

                // Recovery: If we previously showed a warning, clear it
                if (timeoutInfo.warningShown) {
                    if (cardHandlers.size > 0) {
                        const latestCardId = Array.from(cardHandlers.keys()).pop();
                        const progressText = document.querySelector(`#${latestCardId} .progress-text`);
                        if (progressText) {
                            progressText.style.color = '#666';
                        }

                        const progressSquare = document.querySelector(`#${latestCardId} .progress-square, #${latestCardId} .thinking-square`);
                        if (progressSquare) {
                            progressSquare.classList.remove('fast-heartbeat');
                        }
                    }
                    timeoutInfo.warningShown = false;
                }
            } else if (data.status === 'COMPLETED' || data.progress === 100) {
                if (timeoutInfo.inactivityTimer) clearTimeout(timeoutInfo.inactivityTimer);
                window.asyncTimeouts.delete(sessionId);
            }
        }
    }

    // Handle balance updates
    if (data.type === 'balance_update') {
        handleBalanceUpdate(data);
        return;
    }

    // Handle ticker updates
    if (data.type === 'ticker_update') {
        handleTickerUpdate(data);
        return;
    }

    // Handle Table Maker execution updates
    if (data.type === 'table_execution_update') {
        handleTableExecutionUpdate(data);
        return;
    }

    if (data.type === 'table_execution_complete') {
        handleTableExecutionComplete(data);
        return;
    }

    if (data.type === 'table_execution_restructure') {
        handleTableExecutionRestructure(data);
        return;
    }

    if (data.type === 'table_execution_unrecoverable') {
        handleTableExecutionUnrecoverable(data);
        return;
    }

    // Handle general warnings
    if (data.type === 'warning') {
        handleWarning(data);
        return;
    }

    // Handle Reference Check updates
    if (data.type === 'reference_check_progress') {
        handleReferenceCheckProgress(data);
        return;
    }

    if (data.type === 'reference_check_complete') {
        handleReferenceCheckComplete(data);
        return;
    }

    if (data.type === 'reference_check_error') {
        handleReferenceCheckError(data);
        return;
    }

    // Handle Upload Interview updates
    if (data.type === 'upload_interview_update') {
        handleUploadInterviewUpdate(data);
        return;
    }

    if (data.type === 'config_generation_start') {
        handleConfigGenerationStart(data);
        return;
    }

    if (data.type === 'upload_interview_error') {
        handleUploadInterviewError(data);
        return;
    }

    // General error handler
    if (data.type === 'error' || data.type === 'validation_failed' || data.type === 'preview_failed' ||
        data.type === 'config_generation_failed' || data.status === 'FAILED' || data.status === 'ERROR') {

        if (cardHandlers.size > 0) {
            let latestCardId = null;
            let latestOrder = -1;

            for (const [cardId, handlerInfo] of cardHandlers) {
                if (handlerInfo && cardId && handlerInfo.registrationOrder > latestOrder) {
                    latestCardId = cardId;
                    latestOrder = handlerInfo.registrationOrder;
                }
            }

            if (latestCardId) {
                let errorTitle = 'Operation failed';
                if (data.type === 'validation_failed') errorTitle = 'Validation failed';
                else if (data.type === 'preview_failed') errorTitle = 'Preview failed';
                else if (data.type === 'config_generation_failed') errorTitle = 'Generation failed';

                completeThinkingInCard(latestCardId, errorTitle);
                const errorMessage = data.error || data.message || data.status || 'Operation failed';
                showMessage(`${latestCardId}-messages`, `Error: ${errorMessage}`, 'error');
                console.error('General error handled via WebSocket:', data);
            }
        }
        return;
    }

    // Handle progress updates
    const isProgressType = (data.type === 'progress' || data.type === 'config_generation_progress' ||
         data.type === 'progress_update' || data.type === 'config_progress_update' ||
         data.type === 'preview_progress' || data.type === 'table_finalization_progress');
    const hasProgress = data.progress !== undefined;

    if (isProgressType && hasProgress) {
        // Extract confidence score if present
        if (data.confidence_score !== undefined) {
            globalState.confidenceScores.push(data.confidence_score);

            const sum = globalState.confidenceScores.reduce((a, b) => a + b, 0);
            const runningAverage = Math.round(sum / globalState.confidenceScores.length);

            globalState.currentConfidenceScore = runningAverage;
        }

        // Find the last registered card and update it
        let latestCardId = null;
        let latestOrder = -1;

        for (const [cardId, handlerInfo] of cardHandlers) {
            if (handlerInfo && cardId && handlerInfo.registrationOrder > latestOrder) {
                latestCardId = cardId;
                latestOrder = handlerInfo.registrationOrder;
            }
        }

        if (latestCardId) {
            const message = data.status || data.message || null;
            updateThinkingProgress(latestCardId, data.progress, message);

            // Check if this is configuration generation completion
            if (data.progress === 100 && message && (message.includes('Configuration generated') || message.includes('Table generation complete'))) {
                const card = document.getElementById(latestCardId);
                const isTableMakerCard = card && card.querySelector('.card-title')?.textContent.includes('Table Maker');

                if (!isTableMakerCard) {
                    if (data.session_id) globalState.sessionId = data.session_id;
                    if (data.table_filename) globalState.excelFileName = data.table_filename;
                    globalState.excelFileUploaded = true;

                    completeThinkingInCard(latestCardId, 'Configuration generation complete!');

                    if (!message.includes('Configuration generated')) {
                        showMessage(`${latestCardId}-messages`, 'Validation configuration completed! Validating first few rows...', 'success');

                        setTimeout(() => {
                            globalState.activePreviewCard = null;
                            createPreviewCard();
                        }, 800);
                    }
                }
            }
        }
        return;
    }

    // Handle async delegation complete
    if (data.type === 'async_delegation_complete') {
        const maxTimeoutMinutes = data.max_expected_minutes || 30;
        const inactivityTimeoutMs = 3 * 60 * 1000; // 3 minutes

        if (!window.asyncTimeouts) window.asyncTimeouts = new Map();

        const startInactivityTimer = () => {
            const existing = window.asyncTimeouts.get(sessionId);
            if (existing && existing.inactivityTimer) {
                clearTimeout(existing.inactivityTimer);
            }

            const inactivityTimer = setTimeout(() => {
                const timeoutInfo = window.asyncTimeouts.get(sessionId);

                if (timeoutInfo && timeoutInfo.activeProcessing) {
                    if (cardHandlers.size > 0) {
                        const latestCardId = Array.from(cardHandlers.keys()).pop();
                        showValidatorDeathWarning(latestCardId, sessionId);
                    }
                }

                window.asyncTimeouts.delete(sessionId);
            }, inactivityTimeoutMs);

            if (window.asyncTimeouts.has(sessionId)) {
                window.asyncTimeouts.get(sessionId).inactivityTimer = inactivityTimer;
            } else {
                window.asyncTimeouts.set(sessionId, { inactivityTimer });
            }
        };

        startInactivityTimer();
        window.asyncTimeouts.get(sessionId).restartInactivityTimer = startInactivityTimer;
    }

    // Handle completion messages
    if (data.type === 'config_generation_complete' || data.type === 'config_generation_failed') {
        globalState.isProcessingConfig = false;
    }

    // Handle completion messages - track but ALWAYS dispatch to card handler
    // UI updates are idempotent, so duplicates just refresh the same content
    if (data.status === 'COMPLETED') {
        // Determine the source: WebSocket (no _completionSource) or API poll (has _completionSource)
        const source = data._completionSource || 'websocket';

        // Track completion for logging, but DON'T block handler dispatch
        // The card handler is idempotent - safe to call multiple times
        const isFirstCompletion = tryHandleCompletion(source);

        if (!isFirstCompletion) {
            // Log duplicate but STILL dispatch to handler (fixes UI hang bug)
            // The handler will just refresh the same completion UI
            console.log(`[ROUTE] Duplicate COMPLETED from '${source}' - dispatching anyway to ensure UI updates`);
        }

        // Clear async timeouts (safe to call multiple times)
        if (window.asyncTimeouts && window.asyncTimeouts.has(sessionId)) {
            const timeoutInfo = window.asyncTimeouts.get(sessionId);
            if (timeoutInfo && timeoutInfo.inactivityTimer) {
                clearTimeout(timeoutInfo.inactivityTimer);
            }
            window.asyncTimeouts.delete(sessionId);
        }

        // Always dispatch to card handler - UI updates are idempotent
        console.log(`[ROUTE] Dispatching COMPLETED to card handler (source: ${source}, first: ${isFirstCompletion})`);
    }

    // Route ALL messages to the last registered card
    if (cardHandlers.size === 0) {
        console.warn('No card handlers registered for WebSocket message:', data);
        return;
    }

    // Find the card with the highest registration order
    let latestHandler = null;
    let latestCardId = null;
    let latestOrder = -1;

    for (const [cardId, handlerInfo] of cardHandlers) {
        if (handlerInfo && cardId && handlerInfo.registrationOrder > latestOrder) {
            latestHandler = handlerInfo;
            latestCardId = cardId;
            latestOrder = handlerInfo.registrationOrder;
        }
    }

    if (latestHandler && latestCardId) {
        try {
            latestHandler.handler(data, latestCardId);
        } catch (error) {
            console.error(`[ROUTE] Error in card handler for ${latestCardId}:`, error);
            console.error('[ROUTE] Message that caused error:', data);
            // If this was a completion message and the handler failed, log for debugging
            if (data.status === 'COMPLETED') {
                console.error('[ROUTE] CRITICAL: COMPLETED handler threw an exception - UI may not update!');
            }
        }
    } else {
        console.warn('No handler found for WebSocket message:', data);
    }
}

// ============================================
// BALANCE UPDATE HANDLING
// ============================================

function handleBalanceUpdate(data) {
    if (!data || typeof data !== 'object') {
        return;
    }

    const newBalance = data.new_balance;
    const transaction = data.transaction;

    showBalanceNotification(newBalance, transaction);

    if (globalState) {
        globalState.accountBalance = newBalance;
    }
}

function showBalanceNotification(newBalance, transaction) {
    const notification = document.createElement('div');
    notification.className = 'balance-notification';
    notification.innerHTML = `
        <div class="balance-notification-content">
            <div class="balance-notification-icon">💰</div>
            <div class="balance-notification-text">
                <div class="balance-notification-title">Balance Updated</div>
                <div class="balance-notification-amount">
                    ${transaction.amount < 0 ? '-' : '+'}$${Math.abs(transaction.amount).toFixed(4)}
                </div>
                <div class="balance-notification-balance">
                    New balance: $${newBalance.toFixed(4)}
                </div>
                <div class="balance-notification-desc">${transaction.description}</div>
            </div>
            <button class="balance-notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 8000);

    setTimeout(() => {
        notification.classList.add('balance-notification-show');
    }, 100);
}

// ============================================
// WARNING HANDLING
// ============================================

function handleWarning(data) {
    if (!data) return;

    const title = data.title || 'Warning';
    const message = data.message || 'A warning occurred';
    const warningType = data.warning_type || 'general';

    let targetCardId = null;
    if (data.conversation_id) {
        for (const [cardId, handlerInfo] of cardHandlers) {
            if (handlerInfo && handlerInfo.conversationId === data.conversation_id) {
                targetCardId = cardId;
                break;
            }
        }
    }

    // If no specific card found, use the most recent card
    if (!targetCardId && cardHandlers.size > 0) {
        let latestOrder = -1;
        for (const [cardId, handlerInfo] of cardHandlers) {
            if (handlerInfo && handlerInfo.registrationOrder > latestOrder) {
                targetCardId = cardId;
                latestOrder = handlerInfo.registrationOrder;
            }
        }
    }

    if (targetCardId) {
        const formattedMessage = `<strong>${title}</strong><br>${message}`;

        let detailsHtml = '';
        if (data.rows_included) {
            detailsHtml += `<br><em>${data.rows_included} rows included</em>`;
        }

        const messageId = `warning-${warningType}-${Date.now()}`;
        showMessage(
            `${targetCardId}-messages`,
            formattedMessage + detailsHtml,
            'warning',
            false,
            messageId
        );
    } else {
        console.warn('[WARNING] No card found to display warning:', data);
    }
}

function showInsufficientBalanceError(errorData, cardId = null) {
    const balance = globalState.accountBalance || errorData.current_balance || 0;
    const minCost = errorData.estimated_minimum_cost || 0.01;
    const shortfall = Math.max(0, minCost - balance);

    const recommendedMinimum = Math.ceil(shortfall);
    const recommendedSafe = Math.ceil(minCost * 2);

    globalState.pendingValidationRetry = true;
    globalState.hasInsufficientBalance = true;

    const errorMessage = `
        <div class="insufficient-balance-error">
            <div class="error-icon">💳</div>
            <div class="error-content">
                <h4>Need ${recommendedMinimum} Credits</h4>
                <p>You need $${shortfall.toFixed(2)} more credits to run this validation.</p>

                <div class="error-actions">
                    <button class="std-button primary" onclick="needCredits(${recommendedMinimum})" style="width: 100%; margin-bottom: 10px;">
                        <span class="button-text">💳 Get ${recommendedMinimum} Credits</span>
                    </button>
                    <button class="std-button secondary" onclick="checkBalanceAndUpdate(this);">
                        <span class="button-text">🔄 Check Balance</span>
                    </button>
                </div>
            </div>
        </div>
    `;

    if (cardId) {
        showMessage(`${cardId}-messages`, errorMessage, 'error');
    } else {
        const notification = document.createElement('div');
        notification.className = 'balance-error-notification';
        notification.innerHTML = errorMessage;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('balance-error-notification-show');
        }, 100);
    }
}

// ============================================
// TICKER UPDATE HANDLING
// ============================================

function handleTickerUpdate(data) {
    if (!data || typeof data !== 'object') {
        return;
    }

    // Extract ticker information
    const rowIds = data.row_ids || '';
    const column = data.column || '';
    const confidence = data.confidence || '';
    const confidenceEmoji = data.confidence_emoji || '';
    const finalValue = data.final_value || '';
    const explanation = data.explanation || '';

    // Create ticker message
    let tickerMessage = '';
    if (rowIds && column) {
        tickerMessage = `${confidenceEmoji} ${rowIds} - ${column}`;

        // Add truncated value if present
        if (finalValue && finalValue.length > 50) {
            tickerMessage += `: ${finalValue.substring(0, 50)}...`;
        } else if (finalValue) {
            tickerMessage += `: ${finalValue}`;
        }
    } else {
        tickerMessage = data.message || 'Processing...';
    }

    // Display ticker message if we have an active validation card
    if (globalState.activeCardId) {
        const tickerContainer = document.querySelector(`#${globalState.activeCardId} .ticker-message`);
        if (tickerContainer) {
            tickerContainer.textContent = tickerMessage;
        }
    }

    // Also update progress text with confidence info
    if (explanation) {
        const progressText = document.querySelector('.progress-text');
        if (progressText) {
            const currentText = progressText.textContent;
            // Only update if not showing more important information
            if (!currentText.includes('Completing') && !currentText.includes('Processing')) {
                progressText.textContent = explanation;
            }
        }
    }
}

function hideTicker() {
    // Hide all ticker containers
    const tickers = document.querySelectorAll('.ticker-container');
    tickers.forEach(ticker => {
        ticker.style.display = 'none';
    });

    // Clear ticker message
    const tickerMessages = document.querySelectorAll('.ticker-message');
    tickerMessages.forEach(msg => {
        msg.textContent = '';
    });

    // Clear global ticker state
    if (globalState) {
        globalState.tickerMessages = [];
        globalState.currentTickerIndex = 0;
    }
}

function showTicker() {
    // Show ticker container
    const tickers = document.querySelectorAll('.ticker-container');
    tickers.forEach(ticker => {
        ticker.style.display = 'block';
    });
}

function handleProcessingWebSocketMessage(data, cardId) {
    if (data.status === 'PROCESSING') {
        // Handle processing status
    }
}

// Export ticker functions globally
window.hideTicker = hideTicker;
window.showTicker = showTicker;
window.handleTickerUpdate = handleTickerUpdate;

// Export status recovery functions
window.checkValidationStatus = checkValidationStatus;
window.resetCompletionState = resetCompletionState;
window.stopFallbackPolling = stopFallbackPolling;

// Export polling state check (useful for debugging and preventing duplicate starts)
window.isPollingActive = () => activeFallbackPolling !== null;
window.getPollingState = () => activeFallbackPolling ? { ...activeFallbackPolling } : null;

// Export completion state (useful for debugging)
window.getCompletionState = () => ({
    handled: validationCompletionHandled,
    handledBy: completionHandledBy
});

// ============================================
// PAGE VISIBILITY API - Check status when tab becomes visible
// ============================================

document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        // Tab became visible - check if we're in full validation and need to sync
        if (globalState.currentValidationState === 'full' && globalState.sessionId) {
            console.log('[VISIBILITY] Tab became visible during full validation - checking status');

            // Cancel any pending visibility check to prevent duplicates
            if (pendingVisibilityCheck) {
                clearTimeout(pendingVisibilityCheck);
                pendingVisibilityCheck = null;
            }

            // Small delay to allow WebSocket to potentially reconnect first
            pendingVisibilityCheck = setTimeout(async () => {
                pendingVisibilityCheck = null;

                // Double-check we're still in full validation state
                if (globalState.currentValidationState !== 'full' || validationCompletionHandled) {
                    console.log('[VISIBILITY] State changed or completed, skipping check');
                    return;
                }

                const completed = await checkValidationStatus(globalState.sessionId, false, 'visibility_change');
                if (completed) {
                    console.log('[VISIBILITY] Validation completed while tab was hidden');
                }
            }, 1000);
        }
    } else {
        // Tab became hidden - cancel any pending check
        if (pendingVisibilityCheck) {
            clearTimeout(pendingVisibilityCheck);
            pendingVisibilityCheck = null;
        }
    }
});

// ============================================
// ONLINE/OFFLINE HANDLING
// ============================================

window.addEventListener('online', () => {
    console.log('[NETWORK] Browser came online');
    if (globalState.currentValidationState === 'full' && globalState.sessionId) {
        console.log('[NETWORK] Reconnecting WebSocket and checking status');
        ensureWebSocketHealth(globalState.sessionId);

        // Check status after a short delay
        setTimeout(async () => {
            await checkValidationStatus(globalState.sessionId, false, 'network_online');
        }, 2000);
    }
});
