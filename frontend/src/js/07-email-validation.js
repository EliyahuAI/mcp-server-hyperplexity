/* ========================================
 * 07-email-validation.js - Email Validation
 *
 * Handles email validation for gating access to premium features.
 * Provides a reusable email validation card that can be used
 * standalone or as part of a larger flow.
 *
 * Dependencies: 00-config.js, 01-state.js, 02-analytics.js,
 *               03-utility.js, 04-cards.js
 * ======================================== */

/**
 * Creates an email validation card
 * @param {Object} options - Card options
 * @param {string} options.id - Card ID (default: generateCardId())
 * @param {string} options.title - Card title (default: "Email Verification Required")
 * @param {string} options.subtitle - Card subtitle (default: "Verify your email to continue")
 * @param {string} options.infoHeaderText - Info header text
 * @returns {Object} Card info {cardId, card}
 */
function createEmailValidationCard(options = {}) {
    const cardId = options.id || generateCardId();
    const title = options.title || "Email Verification Required";
    const subtitle = options.subtitle || "Verify your email to continue";
    const infoHeaderText = options.infoHeaderText || 'Enter your email address to access this feature. We\'ll send you a verification code.';

    const cardHTML = `
        <div id="${cardId}-form">
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label" for="${cardId}-email">Email Address</label>
                    <input type="email" id="${cardId}-email" class="form-input"
                        placeholder="your.email@example.com" required>
                </div>
            </div>
            <div id="${cardId}-code-section" style="display: none;">
                <div class="privacy-checkbox">
                    <input type="checkbox" id="${cardId}-terms" required>
                    <label for="${cardId}-terms">
                        I agree to the <a href="https://eliyahu.ai/terms" target="_blank" style="color: var(--primary-color); text-decoration: underline;">Terms and Conditions</a>
                    </label>
                </div>
                <div class="privacy-checkbox">
                    <input type="checkbox" id="${cardId}-privacy" required>
                    <label for="${cardId}-privacy">
                        I accept the <a href="https://eliyahu.ai/privacy" target="_blank" style="color: var(--primary-color); text-decoration: underline;">Privacy Notice</a>
                    </label>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" for="${cardId}-code">Verification Code</label>
                        <input type="text" id="${cardId}-code" class="form-input"
                            placeholder="Enter 6-digit code" maxlength="6">
                    </div>
                </div>
            </div>
            <div id="${cardId}-messages"></div>
        </div>
        <div id="${cardId}-buttons"></div>
    `;

    const card = createCard({
        id: cardId,
        icon: '✉️',
        title: title,
        subtitle: subtitle,
        content: cardHTML
    });

    // Create validate button
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Send Code',
            icon: '📧',
            variant: 'primary',
            callback: async (e) => {
                const button = e.target.closest('button');
                await sendEmailCode(cardId, button);
            }
        }
    ]);

    return { cardId, card };
}

async function sendEmailCode(cardId, button) {
    const email = document.getElementById(`${cardId}-email`).value.trim();

    if (!email) {
        showMessage(`${cardId}-messages`, 'Please enter an email address', 'error');
        throw new Error('Email required');
    }

    try {
        globalState.email = email;

        // Check if we should force re-verification (e.g., after logout)
        const forceReverify = sessionStorage.getItem('forceReverify') === 'true';
        if (forceReverify) {
            sessionStorage.removeItem('forceReverify');
        }

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'checkOrSendValidation',
                email: email,
                force_reverify: forceReverify  // Tell backend to send new code
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (data.validated && data.session_token) {
                // Email already validated, backend issued token without sending code
                console.log('[EMAIL] Email already validated, token issued');

                // Store session token
                sessionStorage.setItem('sessionToken', data.session_token);
                globalState.sessionToken = data.session_token;

                // Show message that email is already validated
                showMessage(`${cardId}-messages`, 'Welcome back! Your email is already verified.', 'success');

                // Mark as validated
                globalState.isNewUser = false; // Returning user

                // Brief delay then proceed
                setTimeout(() => {
                    handleEmailValidated(cardId);
                }, 800);
            } else {
                // Code was sent, show verification form
                document.getElementById(`${cardId}-code-section`).style.display = 'block';
                showMessage(`${cardId}-messages`, 'Validation code sent to your email!', 'success');
                document.getElementById(`${cardId}-code`).focus();

                // Update button to verify code
                markButtonSelected(button, '✓ Code Sent');

                // Add verify button
                createButtonRow(`${cardId}-buttons`, [
                    {
                        text: 'Verify Code',
                        icon: '🔐',
                        variant: 'primary',
                        callback: async (e) => {
                            const verifyButton = e.target.closest('button');
                            await verifyCode(cardId, verifyButton);
                        }
                    }
                ]);
            }
        } else {
            showMessage(`${cardId}-messages`, data.message || 'Failed to send code.', 'error');
            throw new Error('Failed to send code');
        }
    } catch (error) {
        console.error('Email validation error:', error);
        throw error;
    }
}

async function verifyCode(cardId, button) {
    const code = document.getElementById(`${cardId}-code`).value.trim();
    const termsCheckbox = document.getElementById(`${cardId}-terms`);
    const privacyCheckbox = document.getElementById(`${cardId}-privacy`);

    // Validate code first
    if (code.length !== 6) {
        showMessage(`${cardId}-messages`, 'Please enter a 6-digit code', 'error');
        throw new Error('Invalid code');
    }

    // Validate checkboxes
    if (!termsCheckbox.checked) {
        showMessage(`${cardId}-messages`, 'Please agree to the Terms and Conditions to continue', 'error');
        throw new Error('Terms not accepted');
    }

    if (!privacyCheckbox.checked) {
        showMessage(`${cardId}-messages`, 'Please accept the Privacy Notice to continue', 'error');
        throw new Error('Privacy not accepted');
    }

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'validateEmailCode',
                email: globalState.email,
                code: code
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // SECURITY: Store session token from backend
            if (data.session_token) {
                sessionStorage.setItem('sessionToken', data.session_token);
                globalState.sessionToken = data.session_token;
            }
            markButtonSelected(button, '✓ Verified');
            // ALWAYS TREAT AS NEW USER FOR NOW
            globalState.isNewUser = true; // Override - show demo to everyone
            handleEmailValidated(cardId);
        } else {
            showMessage(`${cardId}-messages`, data.message || 'Invalid code', 'error');
            throw new Error('Invalid code');
        }
    } catch (error) {
        console.error('Code verification error:', error);
        throw error;
    }
}

function handleEmailValidated(cardId) {
    localStorage.setItem('validatedEmail', globalState.email);

    // Track email validation conversion
    trackEmailValidationConversion(globalState.email);

    // SECURITY: Show signed-in badge
    showSignedInBadge(globalState.email);

    // Check for pending action (deferred email validation mode)
    if (globalState.pendingActionAfterEmail) {
        const pendingAction = globalState.pendingActionAfterEmail;
        const description = globalState.pendingActionDescription || 'continuing';

        // Clear pending action
        globalState.pendingActionAfterEmail = null;
        globalState.pendingActionDescription = null;

        console.log(`[EMAIL] Email validated, executing pending action: ${description}`);

        // Hide email form (showFinalCardState doesn't hide ${cardId}-form)
        const formEl = document.getElementById(`${cardId}-form`);
        if (formEl) formEl.style.display = 'none';

        // Update status badge to show validated
        const card = document.getElementById(cardId);
        if (card) {
            const statusBadge = card.querySelector('.status-badge');
            if (statusBadge) {
                statusBadge.className = 'status-badge completed';
                statusBadge.innerHTML = '<span>Validated</span>';
            }
        }

        // Show success message briefly
        showFinalCardState(cardId, `Email verified! Now ${description}...`, 'success');

        // Execute pending action after brief delay
        setTimeout(() => {
            pendingAction();
        }, 500);

        return;
    }

    // Hide email form
    const formElement = document.getElementById(`${cardId}-form`);
    if (formElement) {
        formElement.style.display = 'none';
    }

    // Show completion message
    showFinalCardState(cardId, 'Email validated! ✓', 'success');

    // Update status badge
    const card = document.getElementById(cardId);
    if (card) {
        const statusBadge = card.querySelector('.status-badge');
        if (statusBadge) {
            statusBadge.className = 'status-badge completed';
            statusBadge.innerHTML = '<span>Validated</span>';
        }
    } else {
        console.error(`Card element ${cardId} not found`);
    }

    // Hide the validate email button
    const buttonsContainer = document.getElementById(`${cardId}-buttons`);
    if (buttonsContainer) {
        buttonsContainer.style.display = 'none';
    }

    // Check page type to determine next card
    const pageType = detectPageType();

    setTimeout(() => {
        if (pageType === 'reference-check') {
            // Reference check mode - go straight to reference check card
            proceedWithReferenceCheck(cardId);
        } else if (globalState.isNewUser) {
            // Default mode - show demo option for new users
            createUploadOrDemoCard();
        } else {
            // Default mode - show upload card for returning users
            createUploadCard();
        }
    }, 500);
}

/* ========================================
 * Signed-In Indicator (Top-Right of First Card)
 * Shows user email with logout button
 * ======================================== */

function showSignedInBadge(email) {
    // Find the first card
    const firstCard = document.querySelector('.card');
    if (!firstCard) {
        // Card doesn't exist yet, retry after a short delay
        console.log('[AUTH] Waiting for first card to appear...');
        setTimeout(() => showSignedInBadge(email), 200);
        return;
    }

    // Remove existing indicator if any
    const existingIndicator = document.querySelector('.card-signed-in-indicator');
    if (existingIndicator) {
        existingIndicator.remove();
    }

    // Create indicator
    const indicator = document.createElement('div');
    indicator.className = 'card-signed-in-indicator';
    indicator.innerHTML = `
        <span class="email">${email}</span>
        <button class="logout-btn" title="Logout">⎋ Logout</button>
    `;

    // Add logout handler to button
    const logoutBtn = indicator.querySelector('.logout-btn');
    logoutBtn.addEventListener('click', handleLogout);

    // Add to card-header (same flex row as icon and title)
    const cardHeader = firstCard.querySelector('.card-header');
    if (cardHeader) {
        cardHeader.appendChild(indicator);
    } else {
        firstCard.appendChild(indicator);
    }

    console.log('[AUTH] Signed-in indicator attached to first card');
}

function hideSignedInBadge() {
    const indicator = document.querySelector('.card-signed-in-indicator');
    if (indicator) {
        indicator.remove();
    }
}

async function handleLogout() {
    // Confirm logout
    if (!confirm('Are you sure you want to logout?\n\nThis will log you out on all devices.')) {
        return;
    }

    // Set flag to prevent state saving during logout
    window.isLoggingOut = true;

    const email = globalState.email;

    // SECURITY: Notify backend to revoke all tokens (logout all devices)
    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Token': sessionStorage.getItem('sessionToken') || ''
            },
            body: JSON.stringify({
                action: 'logout',
                email: email
            })
        });

        if (response.ok) {
            console.log('[AUTH] Server-side logout successful');
        }
    } catch (error) {
        console.warn('[AUTH] Could not notify server of logout:', error);
        // Continue with client-side logout anyway
    }

    // Close any active WebSocket connections
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        console.log('[AUTH] Closing WebSocket connection');
        window.ws.close();
    }

    // Close all session WebSocket connections if they exist
    if (typeof sessionWebSockets !== 'undefined' && sessionWebSockets) {
        console.log('[AUTH] Closing all session WebSockets');
        sessionWebSockets.forEach((ws, sessionId) => {
            ws._intentionallyClosed = true;
            ws.close();
        });
        sessionWebSockets.clear();
    }

    // Clear all auth data
    localStorage.removeItem('validatedEmail');

    // Clear all session storage (including saved state)
    sessionStorage.clear();

    // Re-set only the forceReverify flag after clearing
    sessionStorage.setItem('forceReverify', 'true');

    globalState.email = null;
    globalState.sessionToken = null;
    globalState.sessionId = null;

    console.log('[AUTH] User logged out from all devices, cleared all session state');

    // Hard refresh without reload warning
    window.location.href = window.location.origin + window.location.pathname + '?t=' + Date.now();
}

// Note: Signed-in badge initialization moved to 99-init.js
// This ensures it runs after all modules are loaded
