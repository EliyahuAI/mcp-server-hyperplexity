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

// Bump this to require users to re-accept updated terms
const TERMS_VERSION = "1";

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

    const termsAlreadyAccepted = localStorage.getItem(SK_TERMS) === TERMS_VERSION;

    const termsHTML = termsAlreadyAccepted ? '' : `
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
                </div>`;

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
                ${termsHTML}
                <div class="form-group">
                    <label class="form-label">Verification Code</label>
                    <div class="code-inputs" id="${cardId}-code-inputs">
                        <input type="text" class="code-digit" data-index="0" maxlength="1" inputmode="numeric" autocomplete="one-time-code">
                        <input type="text" class="code-digit" data-index="1" maxlength="1" inputmode="numeric">
                        <input type="text" class="code-digit" data-index="2" maxlength="1" inputmode="numeric">
                        <input type="text" class="code-digit" data-index="3" maxlength="1" inputmode="numeric">
                        <input type="text" class="code-digit" data-index="4" maxlength="1" inputmode="numeric">
                        <input type="text" class="code-digit" data-index="5" maxlength="1" inputmode="numeric">
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
            headers: getAuthHeaders(),
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

                // Store session token (30-day expiration, persists across browser restarts)
                localStorage.setItem(SK_TOKEN, data.session_token);
                globalState.sessionToken = data.session_token;

                // Store email alongside token for auto-reauth after browser restart
                localStorage.setItem(SK_EMAIL, email);
                sessionStorage.setItem('validatedEmail', email);

                // Sync terms acceptance from server
                if (data.terms_accepted_version === TERMS_VERSION) {
                    localStorage.setItem(SK_TERMS, data.terms_accepted_version);
                }

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
                setupCodeDigitInputs(cardId);
                const firstDigit = document.querySelector(`#${cardId}-code-inputs .code-digit[data-index="0"]`);
                if (firstDigit) firstDigit.focus();

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
    // Collect code from 6 individual digit boxes
    const digits = document.querySelectorAll(`#${cardId}-code-inputs .code-digit`);
    const code = Array.from(digits).map(d => d.value.trim()).join('');

    // Validate code first
    if (code.length !== 6) {
        showMessage(`${cardId}-messages`, 'Please enter a 6-digit code', 'error');
        return;
    }

    // Validate checkboxes only if they are present (not already accepted)
    const termsAlreadyAccepted = localStorage.getItem(SK_TERMS) === TERMS_VERSION;
    if (!termsAlreadyAccepted) {
        const termsCheckbox = document.getElementById(`${cardId}-terms`);
        const privacyCheckbox = document.getElementById(`${cardId}-privacy`);

        if (!termsCheckbox.checked) {
            showMessage(`${cardId}-messages`, 'Please agree to the Terms and Conditions to continue', 'error');
            return;
        }

        if (!privacyCheckbox.checked) {
            showMessage(`${cardId}-messages`, 'Please accept the Privacy Notice to continue', 'error');
            return;
        }
    }

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'validateEmailCode',
                email: globalState.email,
                code: code,
                terms_version: TERMS_VERSION
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // SECURITY: Store session token from backend (30-day expiration)
            if (data.session_token) {
                localStorage.setItem(SK_TOKEN, data.session_token);
                globalState.sessionToken = data.session_token;
            }
            // Persist terms acceptance so checkboxes won't show next time
            localStorage.setItem(SK_TERMS, TERMS_VERSION);
            markButtonSelected(button, '✓ Verified');
            // ALWAYS TREAT AS NEW USER FOR NOW
            globalState.isNewUser = true; // Override - show demo to everyone
            if (data.welcome_credit_granted) {
                globalState.accountBalance = data.new_balance || data.welcome_credit_amount || 20;
                // Defer modal slightly so email validation card hides first
                setTimeout(() => showWelcomeCreditModal(data.welcome_credit_amount || 20), 600);
            }
            handleEmailValidated(cardId);
        } else {
            showMessage(`${cardId}-messages`, data.message || 'Invalid code. Please try again.', 'error');
            clearCodeDigits(cardId);
        }
    } catch (error) {
        console.error('Code verification error:', error);
        showMessage(`${cardId}-messages`, 'Network error. Please try again.', 'error');
        clearCodeDigits(cardId);
    }
}

function clearCodeDigits(cardId) {
    const digits = document.querySelectorAll(`#${cardId}-code-inputs .code-digit`);
    digits.forEach(d => d.value = '');
    if (digits.length > 0) digits[0].focus();
}

function setupCodeDigitInputs(cardId) {
    const container = document.getElementById(`${cardId}-code-inputs`);
    if (!container) return;
    const digits = container.querySelectorAll('.code-digit');

    digits.forEach((input, idx) => {
        // Auto-advance on digit entry
        input.addEventListener('input', (e) => {
            const val = e.target.value;
            // Allow only single digit
            if (val && !/^\d$/.test(val)) {
                e.target.value = '';
                return;
            }
            if (val && idx < 5) {
                digits[idx + 1].focus();
            }
        });

        // Backspace navigates to previous box; Enter submits
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !input.value && idx > 0) {
                digits[idx - 1].focus();
                digits[idx - 1].value = '';
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                const verifyBtn = document.querySelector(`#${cardId}-buttons .std-button.primary`);
                if (verifyBtn && !verifyBtn.disabled) verifyBtn.click();
            }
        });

        // Paste handler: distribute digits across all boxes
        input.addEventListener('paste', (e) => {
            e.preventDefault();
            const pasted = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 6);
            for (let i = 0; i < 6; i++) {
                digits[i].value = pasted[i] || '';
            }
            // Focus last filled box or the next empty one
            const focusIdx = Math.min(pasted.length, 5);
            digits[focusIdx].focus();
        });
    });
}

function handleEmailValidated(cardId) {
    // Store email in BOTH sessionStorage and localStorage
    // sessionStorage for current session, localStorage to enable auto-reauth after browser restart
    // Backend validates token ownership via DynamoDB, so localStorage email is safe
    sessionStorage.setItem('validatedEmail', globalState.email);
    localStorage.setItem(SK_EMAIL, globalState.email);

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

        // Hide the entire email verification card
        const card = document.getElementById(cardId);
        if (card) card.style.display = 'none';

        // Execute pending action after brief delay
        setTimeout(() => {
            pendingAction();
            // Re-attach badge to the new visible card
            showSignedInBadge(globalState.email);
        }, 500);

        return;
    }

    // Hide the entire email verification card
    const card = document.getElementById(cardId);
    if (card) card.style.display = 'none';

    // Check page type to determine next card
    const pageType = detectPageType();

    setTimeout(() => {
        if (pageType === 'viewer' || pageType === 'demo') {
            // Viewer/demo mode - card is created by initViewerMode/initDemoMode, just show badge
            showSignedInBadge(globalState.email);
        } else if (pageType === 'reference-check') {
            // Reference check mode - go straight to reference check card
            proceedWithReferenceCheck(cardId);
            showSignedInBadge(globalState.email);
        } else if (globalState.isNewUser) {
            // Default mode - show demo option for new users
            createUploadOrDemoCard();
            showSignedInBadge(globalState.email);
        } else {
            // Default mode - show upload card for returning users
            createUploadCard();
            showSignedInBadge(globalState.email);
        }
    }, 500);
}

/* ========================================
 * Signed-In Indicator (Top-Right of First Card)
 * Shows user email with logout button
 * ======================================== */

function showSignedInBadge(email) {
    // Find the first visible card
    const allCards = document.querySelectorAll('.card');
    const firstCard = Array.from(allCards).find(c => c.style.display !== 'none');
    if (!firstCard) {
        // No visible card yet, retry after a short delay
        console.log('[AUTH] Waiting for visible card to appear...');
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
    indicator.style.cursor = 'pointer';
    indicator.innerHTML = `
        <span class="email">${email}</span>
    `;

    // Click badge → open account card
    indicator.addEventListener('click', () => requireEmailThen(() => initAccountPage(), 'manage your account'));

    // Add to card-header (same flex row as icon and title)
    const cardHeader = firstCard.querySelector('.card-header');
    if (cardHeader) {
        cardHeader.appendChild(indicator);
    } else {
        firstCard.appendChild(indicator);
    }

    // Brief flash to draw attention
    indicator.classList.add('flash-in');
    indicator.addEventListener('animationend', () => indicator.classList.remove('flash-in'), { once: true });

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
    if (!confirm('Are you sure you want to logout?\n\nThis will require email verification with a new code on all devices.')) {
        return;
    }

    // Set flag to prevent state saving during logout
    window.isLoggingOut = true;

    const email = globalState.email;

    // SECURITY: Notify backend of logout (for analytics/logging)
    // Note: Token revocation will be handled separately in the future
    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'logout',
                email: email
            })
        });

        if (response.ok) {
            console.log('[AUTH] Server notified of logout');
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

    // Clear all auth data from this device
    localStorage.removeItem(SK_TOKEN);
    localStorage.removeItem(SK_EMAIL);
    sessionStorage.removeItem('validatedEmail');

    // Clear all session storage (including saved state)
    sessionStorage.clear();

    // Re-set only the forceReverify flag after clearing
    sessionStorage.setItem('forceReverify', 'true');

    globalState.email = null;
    globalState.sessionToken = null;
    globalState.sessionId = null;

    console.log('[AUTH] User logged out from this device, token cleared');

    // Hard refresh without reload warning
    window.location.href = window.location.origin + window.location.pathname + '?t=' + Date.now();
}

// Note: Signed-in badge initialization moved to 99-init.js
// This ensures it runs after all modules are loaded
