/* ========================================
 * 14b-payment-state.js - Payment State Controller
 *
 * Centralizes payment flow state management
 * to eliminate race conditions and ensure
 * auto-trigger works from any balance update source.
 *
 * Dependencies: 00-config.js (globalState), 01-utils.js (showMessage)
 * ======================================== */

// Payment state - centralized tracking of pending processing intent
const paymentState = {
    pendingCardId: null,
    pendingEffectiveCost: null,
    triggerSource: null,
    lastTriggerAttempt: 0,
    intentSetTime: null,        // When the intent was set (for expiry)
    expiryWarningShown: false   // Track if we've shown the expiry warning
};

// Constants for timeout behavior
const INTENT_WARNING_MS = 15 * 60 * 1000;  // 15 minutes - show reminder
const INTENT_EXPIRY_MS = 30 * 60 * 1000;   // 30 minutes - auto-expire

/**
 * Record user's intent to process when they have insufficient balance.
 * Called when user clicks "Process Table" but doesn't have enough credits.
 *
 * @param {string} cardId - The card ID that initiated the processing attempt
 * @param {number} effectiveCost - The cost required to process
 */
function setPendingProcessingIntent(cardId, effectiveCost) {
    console.log(`[PAYMENT_STATE] Setting pending processing intent: cardId=${cardId}, cost=${effectiveCost}`);

    const now = Date.now();
    paymentState.pendingCardId = cardId;
    paymentState.pendingEffectiveCost = effectiveCost;
    paymentState.intentSetTime = now;
    paymentState.expiryWarningShown = false;

    // Also set legacy flags for backward compatibility
    globalState.userAttemptedProcessing = true;
    globalState.hasInsufficientBalance = true;

    // Persist to sessionStorage for tab survival
    try {
        sessionStorage.setItem('pendingProcessing', JSON.stringify({
            cardId,
            effectiveCost,
            timestamp: now
        }));
    } catch (e) {
        console.warn('[PAYMENT_STATE] Could not persist to sessionStorage:', e);
    }

    // Start expiry timer
    startExpiryTimer();
}

/**
 * Clear pending intent (called when processing starts or is cancelled).
 */
function clearPendingProcessingIntent() {
    console.log('[PAYMENT_STATE] Clearing pending processing intent');

    paymentState.pendingCardId = null;
    paymentState.pendingEffectiveCost = null;
    paymentState.intentSetTime = null;
    paymentState.expiryWarningShown = false;

    // Clear legacy flags
    globalState.userAttemptedProcessing = false;
    globalState.hasInsufficientBalance = false;
    globalState.pendingProcessingTrigger = null;

    // Clear expiry timer
    stopExpiryTimer();

    // Clear sessionStorage
    try {
        sessionStorage.removeItem('pendingProcessing');
    } catch (e) {
        // Ignore sessionStorage errors
    }
}

/**
 * Restore pending intent from sessionStorage (e.g., after page reload).
 * Call this on page load to recover pending processing state.
 */
function restorePendingProcessingIntent() {
    try {
        const stored = sessionStorage.getItem('pendingProcessing');
        if (stored) {
            const data = JSON.parse(stored);
            const age = Date.now() - data.timestamp;

            // Only restore if less than 30 minutes old
            if (age < INTENT_EXPIRY_MS) {
                paymentState.pendingCardId = data.cardId;
                paymentState.pendingEffectiveCost = data.effectiveCost;
                paymentState.intentSetTime = data.timestamp;
                paymentState.expiryWarningShown = age >= INTENT_WARNING_MS; // Already past warning time
                globalState.userAttemptedProcessing = true;
                globalState.hasInsufficientBalance = true;
                console.log('[PAYMENT_STATE] Restored pending intent from sessionStorage:', data);

                // Start expiry timer for remaining time
                startExpiryTimer();
                return true;
            } else {
                // Expired, clear it
                console.log('[PAYMENT_STATE] Stored intent expired, clearing');
                sessionStorage.removeItem('pendingProcessing');
            }
        }
    } catch (e) {
        console.warn('[PAYMENT_STATE] Could not restore from sessionStorage:', e);
    }
    return false;
}

// Expiry timer reference
let expiryTimerId = null;
let warningTimerId = null;

/**
 * Start timers for warning and expiry of pending intent.
 */
function startExpiryTimer() {
    stopExpiryTimer(); // Clear any existing timers

    if (!paymentState.intentSetTime) return;

    const now = Date.now();
    const age = now - paymentState.intentSetTime;
    const timeToWarning = INTENT_WARNING_MS - age;
    const timeToExpiry = INTENT_EXPIRY_MS - age;

    // Set warning timer (15 min)
    if (timeToWarning > 0 && !paymentState.expiryWarningShown) {
        warningTimerId = setTimeout(() => {
            showExpiryWarning();
        }, timeToWarning);
    }

    // Set expiry timer (30 min)
    if (timeToExpiry > 0) {
        expiryTimerId = setTimeout(() => {
            handleIntentExpiry();
        }, timeToExpiry);
    } else {
        // Already expired
        handleIntentExpiry();
    }
}

/**
 * Stop expiry timers.
 */
function stopExpiryTimer() {
    if (warningTimerId) {
        clearTimeout(warningTimerId);
        warningTimerId = null;
    }
    if (expiryTimerId) {
        clearTimeout(expiryTimerId);
        expiryTimerId = null;
    }
}

/**
 * Show warning that intent will expire soon.
 */
function showExpiryWarning() {
    if (paymentState.expiryWarningShown) return;
    paymentState.expiryWarningShown = true;

    console.log('[PAYMENT_STATE] Showing expiry warning');

    const containerId = getMessageContainerId();
    if (containerId) {
        const msg = `Still waiting for payment? Your session will timeout in 15 minutes. ` +
                   `<a href="#" onclick="extendPaymentIntent(); return false;">Click here to extend</a>`;
        showMessage(containerId, msg, 'warning', false, 'payment-expiry-warning');
    }
}

/**
 * Handle intent expiry - clear state and notify user.
 */
function handleIntentExpiry() {
    console.log('[PAYMENT_STATE] Intent expired after 30 minutes');

    const containerId = getMessageContainerId();

    // Clear the intent
    clearPendingProcessingIntent();

    // Notify user
    if (containerId) {
        showMessage(containerId,
            `Payment session expired. Please click "Process Table" again when ready.`,
            'warning', false, 'payment-expired');
    }
}

/**
 * Extend the payment intent timer (user clicked "extend" link).
 */
function extendPaymentIntent() {
    if (!paymentState.pendingCardId && !globalState.userAttemptedProcessing) {
        console.log('[PAYMENT_STATE] No intent to extend');
        return;
    }

    console.log('[PAYMENT_STATE] Extending payment intent');

    // Reset the timestamp
    paymentState.intentSetTime = Date.now();
    paymentState.expiryWarningShown = false;

    // Update sessionStorage
    try {
        const stored = sessionStorage.getItem('pendingProcessing');
        if (stored) {
            const data = JSON.parse(stored);
            data.timestamp = paymentState.intentSetTime;
            sessionStorage.setItem('pendingProcessing', JSON.stringify(data));
        }
    } catch (e) {
        // Ignore
    }

    // Restart timers
    startExpiryTimer();

    // Show confirmation
    const containerId = getMessageContainerId();
    if (containerId) {
        showMessage(containerId, `Session extended! You have another 30 minutes.`, 'success', false, 'payment-extended');
    }
}

/**
 * Get the correct message container ID based on pending card or fallback to last container.
 * @returns {string|null} The container ID or null if not found
 */
function getMessageContainerId() {
    // First try: use the pending card ID if available
    if (paymentState.pendingCardId) {
        const specificContainer = document.getElementById(`${paymentState.pendingCardId}-messages`);
        if (specificContainer) {
            return `${paymentState.pendingCardId}-messages`;
        }
    }

    // Fallback: find message containers and use the last visible one
    const containers = document.querySelectorAll('[id$="-messages"]');
    if (containers.length > 0) {
        // Prefer visible containers
        for (let i = containers.length - 1; i >= 0; i--) {
            const container = containers[i];
            if (container.offsetParent !== null) { // Check if visible
                return container.id;
            }
        }
        // If no visible container, use the last one
        return containers[containers.length - 1].id;
    }

    return null;
}

/**
 * Central function called by ALL balance update paths.
 * This is THE function that decides whether to auto-trigger processing.
 *
 * @param {string} source - Where the balance update came from:
 *                          'websocket', 'focus', 'polling', 'manual'
 */
function checkAndTriggerProcessing(source) {
    console.log(`[PAYMENT_STATE] checkAndTriggerProcessing called from '${source}'`);

    // Debounce: prevent rapid-fire triggers (1 second window)
    const now = Date.now();
    if (now - paymentState.lastTriggerAttempt < 1000) {
        console.log('[PAYMENT_STATE] Debounced - too soon since last trigger attempt');
        return;
    }
    paymentState.lastTriggerAttempt = now;

    // Check for pending processing intent
    const hasPendingIntent = paymentState.pendingCardId || globalState.userAttemptedProcessing;
    if (!hasPendingIntent) {
        console.log('[PAYMENT_STATE] No pending processing intent, skipping');
        return;
    }

    // Check if intent has expired (in-memory check)
    if (paymentState.intentSetTime && (now - paymentState.intentSetTime) >= INTENT_EXPIRY_MS) {
        console.log('[PAYMENT_STATE] Intent expired, clearing');
        handleIntentExpiry();
        return;
    }

    // Get current balance and required cost
    const currentBalance = globalState.accountBalance || 0;
    const effectiveCost = paymentState.pendingEffectiveCost ||
                          globalState.effectiveCost ||
                          globalState.estimatedCost || 0;

    console.log(`[PAYMENT_STATE] Balance check: current=${currentBalance}, required=${effectiveCost}`);

    // BUG FIX: Don't trigger if effectiveCost is 0 or not set - cost hasn't been calculated yet
    if (effectiveCost <= 0) {
        console.log('[PAYMENT_STATE] effectiveCost is 0 or negative, skipping trigger (cost not calculated)');
        return;
    }

    if (currentBalance >= effectiveCost) {
        // Sufficient balance - trigger processing!
        console.log(`[PAYMENT_STATE] Sufficient balance! Triggering processing from '${source}'`);
        paymentState.triggerSource = source;
        executeProcessingTrigger();
    } else {
        // Still insufficient - show progress message
        const shortfall = effectiveCost - currentBalance;
        const progress = Math.round((currentBalance / effectiveCost) * 100);
        console.log(`[PAYMENT_STATE] Still insufficient: shortfall=${shortfall}, progress=${progress}%`);
        showPartialPaymentProgress(currentBalance, effectiveCost, shortfall, progress);

        // Refresh the timestamp since user is actively trying to pay
        refreshIntentTimestamp();
    }
}

/**
 * Refresh the intent timestamp when user makes partial payment.
 * This extends the expiry window.
 */
function refreshIntentTimestamp() {
    if (!paymentState.intentSetTime) return;

    paymentState.intentSetTime = Date.now();
    paymentState.expiryWarningShown = false;

    // Update sessionStorage
    try {
        const stored = sessionStorage.getItem('pendingProcessing');
        if (stored) {
            const data = JSON.parse(stored);
            data.timestamp = paymentState.intentSetTime;
            sessionStorage.setItem('pendingProcessing', JSON.stringify(data));
        }
    } catch (e) {
        // Ignore
    }

    // Restart timers with fresh time
    startExpiryTimer();
}

/**
 * Actually trigger the processing.
 * This function handles the UI updates and triggers createProcessingCard.
 */
function executeProcessingTrigger() {
    console.log('[PAYMENT_STATE] Executing processing trigger');

    // Get correct message container
    const containerId = getMessageContainerId();

    // Clear UI messages and show success message
    if (containerId) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = '';
        }
        // BUG FIX: Add emoji for consistency with other success messages
        showMessage(containerId,
            `🎉 Credits detected! Auto-starting validation...`,
            'success', false, 'auto-process');
    }

    // Disable buttons to prevent double-click
    disableProcessButtons();

    // Store the card ID before potentially clearing
    const cardId = paymentState.pendingCardId;

    // BUG FIX: Don't clear intent yet - only clear after confirming we can trigger
    // Try to find a way to trigger processing first
    setTimeout(() => {
        let triggerSucceeded = false;

        // First try: Find and click Process Table button
        const buttons = document.querySelectorAll('button');
        for (const button of buttons) {
            const buttonText = button.textContent || '';
            if (buttonText.includes('Process Table') && !button.disabled) {
                console.log('[PAYMENT_STATE] Clicking Process Table button');
                button.click();
                triggerSucceeded = true;
                break;
            }
        }

        // Second try: call createProcessingCard directly if available
        if (!triggerSucceeded && typeof createProcessingCard === 'function') {
            console.log('[PAYMENT_STATE] Calling createProcessingCard directly');
            createProcessingCard();
            triggerSucceeded = true;
        }

        // Only clear intent if we successfully triggered
        if (triggerSucceeded) {
            clearPendingProcessingIntent();
        } else {
            console.error('[PAYMENT_STATE] Could not find way to trigger processing - intent preserved');
            // Re-enable buttons since we failed
            enableProcessButtons();
            // Show error message
            if (containerId) {
                showMessage(containerId,
                    `Could not auto-start. Please click "Process Table" manually.`,
                    'warning', false, 'auto-process-failed');
            }
        }
    }, 500);
}

/**
 * Disable all Process Table buttons to prevent double-clicking.
 */
function disableProcessButtons() {
    document.querySelectorAll('button').forEach(button => {
        const buttonText = button.textContent || '';
        if (buttonText.includes('Process Table')) {
            button.disabled = true;
            const span = button.querySelector('.button-text, span');
            if (span) {
                span.textContent = 'Processing...';
            }
        }
    });
}

/**
 * Re-enable Process Table buttons (if trigger failed).
 */
function enableProcessButtons() {
    const currentBalance = globalState.accountBalance || 0;
    const effectiveCost = paymentState.pendingEffectiveCost ||
                          globalState.effectiveCost ||
                          globalState.estimatedCost || 0;

    document.querySelectorAll('button').forEach(button => {
        const span = button.querySelector('.button-text, span');
        if (span && span.textContent === 'Processing...') {
            button.disabled = false;
            if (currentBalance >= effectiveCost) {
                span.textContent = `🔍 Process Table ($${effectiveCost.toFixed(2)})`;
            } else {
                const needed = Math.ceil(effectiveCost - currentBalance);
                span.textContent = `💳 Add $${needed.toFixed(2)} Credits`;
            }
        }
    });
}

/**
 * Show progress message when partial payment is received.
 *
 * @param {number} balance - Current balance
 * @param {number} cost - Required cost
 * @param {number} shortfall - Amount still needed
 * @param {number} percent - Percentage funded (0-100)
 */
function showPartialPaymentProgress(balance, cost, shortfall, percent) {
    // Update preview balance displays
    if (typeof updatePreviewBalanceDisplay === 'function') {
        updatePreviewBalanceDisplay();
    }

    // Get correct message container
    const containerId = getMessageContainerId();
    if (containerId) {
        const msg = `💰 Balance: $${balance.toFixed(2)} | Need: $${cost.toFixed(2)} | ` +
                   `Still need $${shortfall.toFixed(2)} more (${percent}% funded)`;
        showMessage(containerId, msg, 'info', false, 'partial-progress');
    }
}

/**
 * Check if there's a pending processing intent.
 * Useful for debugging and conditional logic.
 *
 * @returns {boolean} True if there's a pending intent
 */
function hasPendingProcessingIntent() {
    return !!(paymentState.pendingCardId || globalState.userAttemptedProcessing);
}

/**
 * Get the current payment state for debugging.
 *
 * @returns {Object} Current payment state
 */
function getPaymentState() {
    const now = Date.now();
    const age = paymentState.intentSetTime ? now - paymentState.intentSetTime : null;
    return {
        ...paymentState,
        intentAgeMs: age,
        intentAgeMinutes: age ? Math.round(age / 60000) : null,
        timeToExpiry: age ? Math.max(0, INTENT_EXPIRY_MS - age) : null,
        legacyFlags: {
            userAttemptedProcessing: globalState.userAttemptedProcessing,
            hasInsufficientBalance: globalState.hasInsufficientBalance,
            hasPendingTrigger: !!globalState.pendingProcessingTrigger
        }
    };
}

// Restore any pending intent from sessionStorage on load
restorePendingProcessingIntent();

// Expose functions globally
window.setPendingProcessingIntent = setPendingProcessingIntent;
window.clearPendingProcessingIntent = clearPendingProcessingIntent;
window.checkAndTriggerProcessing = checkAndTriggerProcessing;
window.hasPendingProcessingIntent = hasPendingProcessingIntent;
window.getPaymentState = getPaymentState;
window.restorePendingProcessingIntent = restorePendingProcessingIntent;
window.extendPaymentIntent = extendPaymentIntent;
