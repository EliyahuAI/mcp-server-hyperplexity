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
        <div class="info-header">
            ${infoHeaderText}
        </div>
        <form id="${cardId}-form" class="email-form">
            <label for="${cardId}-email">Email Address</label>
            <input
                type="email"
                id="${cardId}-email"
                name="email"
                placeholder="you@example.com"
                required
                autocomplete="email"
            />

            <div id="${cardId}-code-section" style="display: none; margin-top: 1rem;">
                <label for="${cardId}-code">Verification Code</label>
                <input
                    type="text"
                    id="${cardId}-code"
                    name="code"
                    placeholder="Enter 6-digit code"
                    maxlength="6"
                    pattern="[0-9]{6}"
                    autocomplete="one-time-code"
                />
            </div>

            <div id="${cardId}-terms-section" style="margin-top: 1rem;">
                <label class="checkbox-label">
                    <input type="checkbox" id="${cardId}-terms" required>
                    <span>I agree to the <a href="https://eliyahu.ai/terms" target="_blank">Terms and Conditions</a></span>
                </label>
                <label class="checkbox-label">
                    <input type="checkbox" id="${cardId}-privacy" required>
                    <span>I accept the <a href="https://eliyahu.ai/privacy" target="_blank">Privacy Notice</a></span>
                </label>
            </div>

            <div id="${cardId}-messages"></div>
        </form>
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

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'checkOrSendValidation',
                email: email
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (data.validated) {
                // SECURITY: Store session token from backend
                if (data.session_token) {
                    sessionStorage.setItem('sessionToken', data.session_token);
                    globalState.sessionToken = data.session_token;
                }
                // Already validated - ALWAYS TREAT AS NEW USER FOR NOW
                globalState.isNewUser = true; // Override backend response
                handleEmailValidated(cardId);
            } else {
                // Show code input
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

    if (!termsCheckbox.checked) {
        showMessage(`${cardId}-messages`, 'Please agree to the Terms and Conditions to continue', 'error');
        throw new Error('Terms not accepted');
    }

    if (!privacyCheckbox.checked) {
        showMessage(`${cardId}-messages`, 'Please accept the Privacy Notice to continue', 'error');
        throw new Error('Privacy not accepted');
    }

    if (code.length !== 6) {
        showMessage(`${cardId}-messages`, 'Please enter a 6-digit code', 'error');
        throw new Error('Invalid code');
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
 * Signed-In Badge (Top Left)
 * Shows user email with logout option
 * ======================================== */

function showSignedInBadge(email) {
    // Remove existing badge if any
    const existingBadge = document.querySelector('.signed-in-badge');
    if (existingBadge) {
        existingBadge.remove();
    }

    // Create badge
    const badge = document.createElement('div');
    badge.className = 'signed-in-badge';
    badge.title = 'Click to logout';
    badge.innerHTML = `
        <span class="email">${email}</span>
        <span class="logout-icon">⎋</span>
    `;

    // Add click handler for logout
    badge.addEventListener('click', handleLogout);

    // Add to body
    document.body.appendChild(badge);

    // Show with animation
    setTimeout(() => {
        badge.style.display = 'flex';
        badge.style.alignItems = 'center';
    }, 100);
}

function hideSignedInBadge() {
    const badge = document.querySelector('.signed-in-badge');
    if (badge) {
        badge.style.display = 'none';
        setTimeout(() => badge.remove(), 300);
    }
}

function handleLogout() {
    // Confirm logout
    if (!confirm('Are you sure you want to logout?')) {
        return;
    }

    // Clear all auth data
    localStorage.removeItem('validatedEmail');
    sessionStorage.removeItem('sessionToken');
    globalState.email = null;
    globalState.sessionToken = null;

    // Hide badge
    hideSignedInBadge();

    // Show logout message
    const cardId = generateCardId();
    createCard({
        id: cardId,
        icon: '👋',
        title: 'Logged Out',
        subtitle: 'You have been logged out successfully',
        content: `
            <div class="info-header">
                Your session has been cleared. Reload the page to login again.
            </div>
        `
    });

    console.log('[AUTH] User logged out');
}

// Initialize signed-in badge on page load if user is validated
if (typeof window !== 'undefined') {
    window.addEventListener('DOMContentLoaded', () => {
        const validatedEmail = localStorage.getItem('validatedEmail');
        const sessionToken = sessionStorage.getItem('sessionToken');

        if (validatedEmail && sessionToken) {
            showSignedInBadge(validatedEmail);
            globalState.email = validatedEmail;
            globalState.sessionToken = sessionToken;
        }
    });
}
