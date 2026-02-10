/* ========================================
 * 14-account.js - Account & Balance Management
 *
 * Handles credit purchasing, balance updates,
 * order polling, and balance notifications.
 *
 * Dependencies: 00-config.js, 05-chat.js
 * ======================================== */

function addCreditsToCart(quantity) {
    if (!quantity || quantity < 1) {
        console.warn('[CREDITS] Invalid quantity:', quantity);
        return false;
    }

    // Find the quantity input
    const quantityInput = document.querySelector('input[name="quantity-input"]');
    if (!quantityInput) {
        console.warn('[CREDITS] Quantity input not found. Make sure the product component is on the page.');
        return false;
    }

    // Find the add-to-cart button
    const addToCartButton = document.querySelector('.sqs-add-to-cart-button');
    if (!addToCartButton) {
        console.warn('[CREDITS] Add-to-cart button not found.');
        return false;
    }

    // Set the quantity
    quantityInput.value = quantity;

    // Trigger input events to make sure the UI updates
    const inputEvent = new Event('input', { bubbles: true });
    const changeEvent = new Event('change', { bubbles: true });
    quantityInput.dispatchEvent(inputEvent);
    quantityInput.dispatchEvent(changeEvent);

    // Click the add-to-cart button
    setTimeout(() => {
        addToCartButton.click();
    }, 500);

    return true;
}

/**
 * Add credits and redirect to cart page
 * @param {number} quantity - Number of credits to add
 */
function addCreditsAndGoToCart(quantity) {
    if (!quantity || quantity < 1) {
        console.warn('[CREDITS] Invalid quantity for purchase:', quantity);
        // Just go to cart if invalid quantity
        window.open('https://eliyahu.ai/cart', '_blank');
        return;
    }

    const success = addCreditsToCart(quantity);

    if (success) {
        // Wait for cart to update, then open cart in new tab
        setTimeout(() => {
            window.open('https://eliyahu.ai/cart', '_blank');
        }, 1500);
    } else {
        // Fallback: open cart in new tab
        window.open('https://eliyahu.ai/cart', '_blank');
    }
}

/**
 * Main function for when user needs credits
 * @param {number} quantity - Number of credits needed
 */
function needCredits(quantity) {
    addCreditsAndGoToCart(quantity);
}

/**
 * Check if the product component is available on the page
 * @returns {boolean} True if components are found
 */
function checkProductComponent() {
    const quantityInput = document.querySelector('input[name="quantity-input"]');
    const addButton = document.querySelector('.sqs-add-to-cart-button');
    const increaseBtn = document.querySelector('.increase-button');
    const decreaseBtn = document.querySelector('.decrease-button');

    return !!(quantityInput && addButton);
}

// Expose credit purchasing functions globally
window.creditPurchasing = {
    addToCart: addCreditsToCart,
    addAndGoToCart: addCreditsAndGoToCart,
    needCredits: needCredits,
    checkComponent: checkProductComponent
};

// Also expose individual functions for console use
window.needCredits = needCredits;
window.addCreditsToCart = addCreditsToCart;
window.addCreditsAndGoToCart = addCreditsAndGoToCart;
window.checkProductComponent = checkProductComponent;

// Check if product component is available on page load
setTimeout(() => {
    const componentAvailable = checkProductComponent();
    if (componentAvailable) {
    } else {
    }
}, 1000);

function handleBalanceUpdate(data) {
    // Safety check: ensure data is valid
    if (!data || typeof data !== 'object') {
        return;
    }

    const newBalance = data.new_balance;
    const transaction = data.transaction;

    // Show balance notification
    showBalanceNotification(newBalance, transaction);

    // Update global state if needed
    if (globalState) {
        globalState.accountBalance = newBalance;
    }
}

function showBalanceNotification(newBalance, transaction) {
    // Create floating notification
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

    // Auto-remove after 8 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 8000);

    // Fade in animation
    setTimeout(() => {
        notification.classList.add('balance-notification-show');
    }, 100);
}

// Handle general warning messages from WebSocket
function handleWarning(data) {
    if (!data) return;

    const title = data.title || 'Warning';
    const message = data.message || 'A warning occurred';
    const warningType = data.warning_type || 'general';

    // Find the most recent card to show the warning
    let targetCardId = null;
    if (data.conversation_id) {
        // If conversation_id is provided, try to find matching card
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
        // Format warning message with title
        const formattedMessage = `<strong>${title}</strong><br>${message}`;

        // Add any additional details if provided
        let detailsHtml = '';
        if (data.rows_included) {
            detailsHtml += `<br><em>${data.rows_included} rows included</em>`;
        }

        // Show warning in the card's message container
        const messageId = `warning-${warningType}-${Date.now()}`;
        showMessage(
            `${targetCardId}-messages`,
            formattedMessage + detailsHtml,
            'warning',
            false,
            messageId
        );

        // Warning displayed
    } else {
        // No card available - log warning
        console.warn('[WARNING] No card found to display warning:', data);
    }
}

function showInsufficientBalanceError(errorData, cardId = null) {
    // Use the current balance from global state (same as preview cards)
    const balance = globalState.accountBalance || errorData.current_balance || 0;
    const minCost = errorData.estimated_minimum_cost || 0.01;
    // Domain multiplier hidden from frontend
    const shortfall = Math.max(0, minCost - balance);

    // Calculate recommended purchase amounts
    const recommendedMinimum = Math.ceil(shortfall); // Round up to nearest dollar
    const recommendedSafe = Math.ceil(minCost * 2); // 2x the minimum cost for multiple validations, rounded up to dollar

    // Set pending retry flag for post-purchase flow
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
        // Show as modal or notification
        const notification = document.createElement('div');
        notification.className = 'balance-error-notification';
        notification.innerHTML = errorMessage;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('balance-error-notification-show');
        }, 100);
    }
}

function openAddCreditsPage(recommendedAmount = null, messageContainer = 'messages') {
    // Get current session info for tracking
    const sessionId = globalState.sessionId || 'no-session';
    const userEmail = getCurrentUserEmail() || '';

    // Calculate recommended amount if not provided
    if (!recommendedAmount && globalState.lastInsufficientBalanceError) {
        const errorData = globalState.lastInsufficientBalanceError;
        const shortfall = Math.max(0, (errorData.estimated_minimum_cost || 0.01) - (errorData.current_balance || 0));
        recommendedAmount = Math.ceil(shortfall); // Round up to nearest dollar
    }

    // Show confirmation message
    const creditsText = recommendedAmount ? `${recommendedAmount}` : 'some';

    // Check if product component is available on the current page
    const hasProductComponent = checkProductComponent();

    if (hasProductComponent && recommendedAmount) {
        // Use automatic credit purchasing if component is available

        // Use the needCredits function for automatic purchasing
        setTimeout(() => {
            needCredits(recommendedAmount);
            // Show instruction to return after purchase
            setTimeout(() => {
                showMessage(messageContainer, `💳 Credits added to cart! Please complete purchase and return to this tab.`, 'info', false, 'return-instruction');
            }, 1500);
        }, 1000);

        // IMPORTANT: Also set up balance refresh when using product component
        // This was missing and caused auto-processing not to trigger on return
        globalState.awaitingBalanceRefresh = true;
        setupBalanceRefreshOnReturn(messageContainer);

    } else {
        // Fall back to opening store page manually (product component not available)
        showMessage(messageContainer, `💳 You need ${creditsText} credits. Opening store in new tab...`, 'info', false, 'store-opening');

        // Build store URL - use environment-specific URL
        const storeUrl = ENV_CONFIG.storeUrl;

        // Add query parameters for tracking
        const params = new URLSearchParams();
        if (recommendedAmount) {
            params.append('amount', recommendedAmount.toFixed(2));
        }
        if (sessionId) {
            params.append('session', sessionId);
        }
        if (userEmail) {
            params.append('email', userEmail);
        }
        params.append('return_to', window.location.href);

        // Create the full URL
        const fullUrl = `${storeUrl}?${params.toString()}`;

        window.open(fullUrl, '_blank');

        // Set flag to refresh balance when user returns
        globalState.awaitingBalanceRefresh = true;

        // Update the same message instead of creating a new one
        setTimeout(() => {
            showMessage(messageContainer, `💳 Opening store with ${creditsText} credits. Your balance will refresh when you return.`, 'info', false, 'store-opening');
        }, 500);

        // Setup balance refresh with proper messaging (only when insufficient balance)
        setupBalanceRefreshOnReturn(messageContainer);
    }
}

// Add window focus event listener to refresh balance when user returns
let windowFocusHandler = null;
let lastFocusTime = 0;

function setupBalanceRefreshOnReturn(messageContainer = 'messages') {
    if (windowFocusHandler) {
        window.removeEventListener('focus', windowFocusHandler);
    }

    windowFocusHandler = async () => {
        const now = Date.now();

        // Avoid rapid-fire focus events (debounce to 2 seconds)
        if (now - lastFocusTime < 2000) {
            return;
        }
        lastFocusTime = now;

        if (globalState.awaitingBalanceRefresh) {
            globalState.awaitingBalanceRefresh = false;

            // Show loading message with specific ID
            showMessage(messageContainer, '🔄 Checking for balance updates...', 'info', false, 'balance-check');

            // Wait a moment for any webhook processing to complete
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Refresh balance for current email
            await refreshCurrentBalance();

            // Check for orders once on return, then start polling
            const foundCredits = await checkForNewOrders(messageContainer);
            if (!foundCredits) {
                // Only start polling if no credits were found immediately
                setTimeout(() => startOrderPolling(messageContainer), 2000);
            }
        } else {
            // Check balance once when returning to tab
            await refreshCurrentBalance();
            const oldBalance = globalState.accountBalance || 0;

            // Check if we have sufficient balance before checking for orders
            const currentBalance = globalState.accountBalance || 0;
            const estimatedCost = globalState.estimatedCost || 0;
            const effectiveCost = globalState.effectiveCost ?? estimatedCost; // Use ?? not || so 0 doesn't fall back
            const hasSufficientBalance = currentBalance >= effectiveCost;

            // Only check for new orders if we don't have sufficient balance
            if (!hasSufficientBalance) {
                try {
                    await checkForNewOrders('messages', false); // Don't show status message (will refresh balance if orders found)
                } catch (error) {
                    console.error('[FOCUS] Error checking orders:', error);
                }
            }

            // Get new balance (may have been updated by checkForNewOrders)
            const newBalance = globalState.accountBalance || 0;

            if (oldBalance !== newBalance) {
                // Update all balance displays
                updateAllBalanceDisplays();
            }

            // Delegate auto-trigger logic to central payment controller
            // This handles ALL cases: balance changed, balance already sufficient, etc.
            if (typeof checkAndTriggerProcessing === 'function') {
                console.log('[FOCUS] Balance check complete, delegating to payment controller');
                checkAndTriggerProcessing('focus');
            } else {
                // Fallback: just update displays if controller not available
                setTimeout(() => {
                    updatePreviewBalanceDisplay();
                }, 500);
            }
        }
    };

    window.addEventListener('focus', windowFocusHandler);
}

// Set up global balance refresh on focus (always active)
setupBalanceRefreshOnReturn();

// Enhanced check balance function with UI feedback
window.checkBalanceAndUpdate = async function(buttonElement) {
    const originalText = buttonElement.querySelector('.button-text').textContent;
    const buttonText = buttonElement.querySelector('.button-text');

    // Show loading state
    buttonText.textContent = '🔄 Checking...';
    buttonElement.disabled = true;

    try {
        // Refresh balance once
        await refreshCurrentBalance();
        const oldBalance = globalState.accountBalance || 0;

        // Check if we have sufficient balance before checking for orders
        const estimatedCost = globalState.estimatedCost || 0;
        const effectiveCost = globalState.effectiveCost ?? estimatedCost; // Use ?? not || so 0 doesn't fall back
        const hasSufficientBalance = oldBalance >= effectiveCost;

        // Only check for new orders if we don't have sufficient balance
        if (!hasSufficientBalance) {
            buttonText.textContent = '🔍 Checking orders...';
            try {
                await checkForNewOrders('messages', false); // Will refresh balance if orders found
            } catch (orderError) {
                console.error('[BALANCE_CHECK] Order check failed:', orderError);
            }
        }

        // Get new balance (may have been updated by checkForNewOrders)
        const newBalance = globalState.accountBalance || 0;

        // Update all displays
        updateAllBalanceDisplays();

        // Show button feedback based on balance change
        if (newBalance !== oldBalance) {
            buttonText.textContent = `✅ $${newBalance.toFixed(2)}`;
        } else {
            buttonText.textContent = `✓ $${newBalance.toFixed(2)}`;
        }

        // Delegate auto-trigger logic to central payment controller
        if (typeof checkAndTriggerProcessing === 'function') {
            console.log('[MANUAL] Balance checked, delegating to payment controller');
            checkAndTriggerProcessing('manual');
        }

        // Reset button text after delay
        setTimeout(() => {
            buttonText.textContent = originalText;
        }, 2000);

    } catch (error) {
        console.error('[BALANCE_CHECK] Error:', error);
        buttonText.textContent = '❌ Error';
        setTimeout(() => {
            buttonText.textContent = originalText;
        }, 2000);
    } finally {
        buttonElement.disabled = false;
    }
};

// Manual order check function for testing
window.manualOrderCheck = async function() {
    try {
        const result = await checkForNewOrders('messages', true);
        return result;
    } catch (error) {
        console.error('[MANUAL] Order check failed:', error);
        return false;
    }
};

// Order polling state with exponential backoff
let orderPollingTimeout = null;
let pollingAttempts = 0;
const MAX_POLLING_ATTEMPTS = 12; // With exponential backoff: 2s, 4s, 8s, 16s, 32s, 60s... = ~5 minutes total
const INITIAL_POLL_DELAY = 2000; // Start with 2 seconds
const MAX_POLL_DELAY = 60000; // Cap at 60 seconds

function startOrderPolling(messageContainer = 'messages') {
    // Clear any existing polling
    stopOrderPolling();

    pollingAttempts = 0;

    // Start first poll immediately
    pollForOrders(messageContainer);
}

async function pollForOrders(messageContainer) {
    pollingAttempts++;

    try {
        // Always check but only show status messages occasionally to reduce spam
        const shouldShowMessage = pollingAttempts % 3 === 1;
        const foundCredits = await checkForNewOrders(messageContainer, shouldShowMessage);

        if (foundCredits) {
            stopOrderPolling();
            return;
        }

        if (pollingAttempts >= MAX_POLLING_ATTEMPTS) {
            const timeoutEl = showMessage(messageContainer, '⏰ Complete your purchase when ready! Return to this tab after checkout to continue.', 'info', false, 'polling-timeout');

            // Make the timeout message clickable to retry validation
            if (timeoutEl) {
                timeoutEl.style.cursor = 'pointer';
                timeoutEl.onclick = () => {
                    // Clear the timeout message and try to find a retry button or validation card
                    timeoutEl.remove();
                    const validationCards = document.querySelectorAll('.validation-card');
                    if (validationCards.length > 0) {
                        const lastCard = validationCards[validationCards.length - 1];
                        const processButton = lastCard.querySelector('button[data-action*="process"], button:contains("Process")');
                        if (processButton) {
                            processButton.click();
                        }
                    }
                };
            }

            stopOrderPolling();
            return;
        }

        // Calculate next delay with exponential backoff
        const delay = Math.min(INITIAL_POLL_DELAY * Math.pow(2, pollingAttempts - 1), MAX_POLL_DELAY);
        // Next order check scheduled

        // Schedule next poll
        orderPollingTimeout = setTimeout(() => pollForOrders(messageContainer), delay);

    } catch (error) {
        console.error('[POLLING] Error during polling:', error);

        // On error, retry with exponential backoff
        const delay = Math.min(INITIAL_POLL_DELAY * Math.pow(2, pollingAttempts - 1), MAX_POLL_DELAY);
        orderPollingTimeout = setTimeout(() => pollForOrders(messageContainer), delay);
    }
}

function stopOrderPolling() {
    if (orderPollingTimeout) {
        clearTimeout(orderPollingTimeout);
        orderPollingTimeout = null;
    }
    pollingAttempts = 0;
}

// Make polling functions globally accessible
window.startOrderPolling = startOrderPolling;
window.stopOrderPolling = stopOrderPolling;

window.checkForNewOrders = async function checkForNewOrders(messageContainer = 'messages', showStatusMessage = true) {
    try {
        const currentEmail = getCurrentUserEmail();
        if (!currentEmail) {
            return;
        }

        // Trigger Squarespace order check with consistent message ID
        if (showStatusMessage) {
            showMessage(messageContainer, '🔄 Checking for new credit purchases...', 'info', false, 'order-check');
        }

        const orderCheckResponse = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'checkSquarespaceOrders',
                email: currentEmail
            })
        });

        if (orderCheckResponse.ok) {
            const orderData = await orderCheckResponse.json();

            if (orderData.credits_added && orderData.credits_added > 0) {
                // Clear all blue info messages first
                const container = document.getElementById(messageContainer);
                if (container) {
                    const infoMessages = container.querySelectorAll('.message-info');
                    infoMessages.forEach(msg => msg.remove());
                }

                // Immediately refresh the balance and update UI
                await refreshCurrentBalance();

                // Update all displays
                updatePreviewBalanceDisplay();
                updateAllBalanceDisplays();

                // Delegate auto-trigger logic to central payment controller
                // Don't show redundant messages - the controller handles messaging
                if (typeof checkAndTriggerProcessing === 'function') {
                    console.log('[POLLING] Credits added, delegating to payment controller');
                    checkAndTriggerProcessing('polling');
                }

                return true; // Credits were added
            }
        }
        return false; // No credits added
    } catch (error) {
        console.error('Error checking for new orders:', error);
        return false;
    }
}

function updatePreviewBalanceDisplay() {
    // Find the active preview card and update its balance display
    const previewCard = document.querySelector('.card-content[id*="preview"]');
    if (!previewCard) return;

    const estimatesEl = previewCard.querySelector('.estimates');
    if (!estimatesEl) return;

    const currentBalance = globalState.accountBalance || 0;

    // Get estimated cost from the preview card itself
    let estimatedCost = 0;
    const costItems = estimatesEl.querySelectorAll('.cost-item');
    for (const item of costItems) {
        const label = item.querySelector('.cost-label');
        const value = item.querySelector('.cost-value');
        if (label && value && label.textContent.includes('Est. Cost')) {
            estimatedCost = parseFloat(value.textContent.replace('$', '')) || 0;
            break;
        }
    }

    // Fallback to global state if not found in preview
    if (estimatedCost === 0) {
        estimatedCost = globalState.estimatedCost || 0;
    }

    // Use effective cost (net cost after discount) for balance checks
    const effectiveCost = globalState.effectiveCost ?? estimatedCost; // Use ?? not || so 0 doesn't fall back
    const sufficientBalance = currentBalance >= effectiveCost;

    // Find and update the balance line
    for (const item of costItems) {
        const label = item.querySelector('.cost-label');
        if (label && label.textContent.includes('Your Balance')) {
            const valueEl = item.querySelector('.cost-value');
            if (valueEl) {
                valueEl.textContent = `$${currentBalance.toFixed(2)}`;
                // Add a brief highlight to show it updated
                valueEl.style.background = '#e8f5e8';
                valueEl.style.transition = 'background 2s';
                setTimeout(() => {
                    valueEl.style.background = '';
                }, 2000);
            }
            break;
        }
    }

    // Update or hide the credits needed section
    for (const item of costItems) {
        const label = item.querySelector('.cost-label');
        if (label && label.textContent.includes('Credits Needed')) {
            if (sufficientBalance) {
                item.style.display = 'none'; // Hide credits needed line
            } else {
                item.style.display = ''; // Show credits needed line
                const valueEl = item.querySelector('.cost-value');
                if (valueEl) {
                    const creditsNeeded = Math.max(0, effectiveCost - currentBalance);
                    valueEl.textContent = `$${creditsNeeded.toFixed(2)}`;
                }
            }
            break;
        }
    }

    // Update the main action button
    const cardElement = previewCard.closest('.card');
    if (cardElement) {
        const cardId = cardElement.id;
        const buttonsContainer = document.getElementById(`${cardId}-buttons`);
        if (buttonsContainer) {
            // Find the main action button (Process/Add Credits)
            const buttons = buttonsContainer.querySelectorAll('.std-button');
            const mainButton = Array.from(buttons).find(btn => {
                const text = btn.textContent;
                return text.includes('Process Table') || text.includes('Add Credits');
            });

            if (mainButton) {
                const buttonText = mainButton.querySelector('.button-text');
                if (buttonText) {
                    if (sufficientBalance) {
                        // Update to Process button
                        buttonText.textContent = `🔍 Process Table ($${effectiveCost.toFixed(2)})`;
                        mainButton.className = mainButton.className.replace('secondary', 'primary');
                    } else {
                        // Update to Add Credits button
                        const creditsNeeded = Math.max(0, effectiveCost - currentBalance);
                        buttonText.textContent = `💳 Add $${creditsNeeded.toFixed(2)} Credits`;
                        mainButton.className = mainButton.className.replace('primary', 'secondary');

                        // Update the callback
                        mainButton.onclick = async (e) => {
                            const button = e.target.closest('button');
                            globalState.hasInsufficientBalance = true;
                            markButtonSelected(button, '💳 Opening store...');
                            const recommendedAmount = Math.ceil(creditsNeeded);
                            openAddCreditsPage(recommendedAmount, `${cardId}-messages`);

                            setTimeout(() => {
                                markButtonUnselected(button);
                            }, 3000);
                        };
                    }
                }
            }
        }
    }
}

// Make the function globally accessible for testing
window.updatePreviewBalanceDisplay = updatePreviewBalanceDisplay;

function updateAllBalanceDisplays() {
    // Update preview cards
    updatePreviewBalanceDisplay();

    // Update any balance display elements
    const balanceElements = document.querySelectorAll('.balance-amount, .current-balance, [data-balance]');
    balanceElements.forEach(el => {
        if (globalState.accountBalance !== undefined) {
            el.textContent = `$${globalState.accountBalance.toFixed(2)}`;
        }
    });

    // Update credits needed displays
    const creditsNeededElements = document.querySelectorAll('.credits-needed, [data-credits-needed]');
    creditsNeededElements.forEach(el => {
        const estimatedCost = globalState.lastInsufficientBalanceError?.estimated_minimum_cost || 0;
        const currentBalance = globalState.accountBalance || 0;
        const needed = Math.max(0, estimatedCost - currentBalance);
        if (needed <= 0) {
            el.textContent = 'Sufficient Balance';
            el.style.color = '#4CAF50';
        } else {
            el.textContent = `$${needed.toFixed(2)}`;
            el.style.color = '#f44336';
        }
    });
}

window.refreshCurrentBalance = async function refreshCurrentBalance() {
    try {
        const currentEmail = getCurrentUserEmail();
        if (!currentEmail) {
            return;
        }

        // Now get the updated balance
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'getAccountBalance',
                email: currentEmail
            })
        });

        if (response.ok) {
            const data = await response.json();

            if (data.success) {
                // Handle different response formats
                let newBalance = data.balance;

                // Check various possible locations for balance
                if (newBalance === undefined && data.account_info) {
                    newBalance = data.account_info.balance || data.account_info.current_balance;
                }

                // Also check if balance is a string that needs parsing
                if (typeof newBalance === 'string') {
                    newBalance = parseFloat(newBalance);
                }

                if (newBalance !== undefined && !isNaN(newBalance)) {
                    // Update global balance state
                    const oldBalance = globalState.accountBalance || 0;
                    globalState.accountBalance = newBalance;

                    // If there was a pending validation, clear insufficient balance flag
                    if (globalState.pendingValidationRetry && newBalance > oldBalance) {
                        // Clear insufficient balance flag when balance increases
                        globalState.hasInsufficientBalance = false;
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error refreshing balance:', error);
        // Don't show balance refresh errors to avoid message spam
    }
}

function getCurrentUserEmail() {
    // Try to get email from various possible sources
    const emailInputs = document.querySelectorAll('input[type="email"]');
    for (const input of emailInputs) {
        if (input.value && input.value.includes('@')) {
            return input.value;
        }
    }

    // Try stored email
    const storedEmail = sessionStorage.getItem('validatedEmail');
    if (storedEmail && storedEmail.includes('@')) {
        return storedEmail;
    }

    // Try globalState email
    if (globalState.email && globalState.email.includes('@')) {
        return globalState.email;
    }

    return null;
}
