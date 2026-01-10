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
        ws._lastMessageTime = Date.now();

        try {
            // Check if this is a pong response
            if (event.data === 'pong' || event.data === 'Pong' || event.data === '"pong"') {
                ws._pongsReceived++;
                return; // Don't route pong messages
            }

            const data = JSON.parse(event.data);

            // Validate data is not null/undefined before routing
            if (data && typeof data === 'object') {
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

            // Special handling for full validation disconnections
            if (globalState.currentValidationState === 'full' && globalState.activeCardId) {
                const messageContainer = `${globalState.activeCardId}-messages`;
                const emailAddress = globalState.currentEmail || 'your registered email';

                showMessage(
                    messageContainer,
                    `<strong>Connection Lost</strong><br><br>
                    Don't worry - your validation is still running on our servers and will be emailed to <strong>${emailAddress}</strong> when complete.<br><br>
                    If you don't receive it within 30 minutes, please contact <a href="mailto:eliyahu@eliyahu.ai?subject=Validation%20${sessionId}">eliyahu@eliyahu.ai</a> with session ID: <code>${sessionId}</code>`,
                    'warning',
                    false
                );
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

function setupWebSocketFallback(sessionId) {
    // Poll for completion if WebSocket messages aren't coming through
    const fallbackInterval = setInterval(async () => {
        if (!sessionWebSockets.has(sessionId)) {
            clearInterval(fallbackInterval);
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'checkStatus',
                    session_id: sessionId
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.status === 'completed' || data.preview_data) {
                    ensureProcessingState();
                    globalState.processingState.validationCompleted = true;
                    globalState.workflowPhase = 'completed';

                    routeMessage({
                        status: 'COMPLETED',
                        preview_data: data.preview_data,
                        ...data
                    }, sessionId);
                    clearInterval(fallbackInterval);
                }
            }
        } catch (error) {
            console.error(`Fallback check failed for session ${sessionId}:`, error);
        }
    }, 5000); // Check every 5 seconds

    // Stop checking after 3 minutes
    setTimeout(() => {
        clearInterval(fallbackInterval);
    }, 180000);
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

    // Cancel timeout if we receive a completion message
    if (data.status === 'COMPLETED' && window.asyncTimeouts && window.asyncTimeouts.has(sessionId)) {
        clearTimeout(window.asyncTimeouts.get(sessionId));
        window.asyncTimeouts.delete(sessionId);
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
        latestHandler.handler(data, latestCardId);
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
