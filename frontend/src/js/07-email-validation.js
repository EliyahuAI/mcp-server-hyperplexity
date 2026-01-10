/* ========================================
 * 07-email-validation.js - Email Verification
 *
 * Handles email validation, code sending,
 * and verification flow.
 *
 * Dependencies: 00-config.js, 04-cards.js, 05-chat.js
 * ======================================== */

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function createEmailCard() {
    const cardId = generateCardId();
    const content = `
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
                        I agree to the <a href="${ENV_CONFIG.termsUrl}" target="_blank" style="color: var(--primary-color); text-decoration: underline;">Terms and Conditions</a>
                    </label>
                </div>
                <div class="privacy-checkbox">
                    <input type="checkbox" id="${cardId}-privacy">
                    <label for="${cardId}-privacy">
                        I accept the <a href="${ENV_CONFIG.privacyUrl}" target="_blank" style="color: var(--primary-color); text-decoration: underline;">Privacy Notice</a>
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
        <div id="${cardId}-success" style="display: none;">
            <div class="message message-success">
                <span class="message-icon">✓</span>
                <span>Email validated successfully!</span>
            </div>
        </div>
    `;

    const card = createCard({
        id: cardId,  // Pass explicit ID
        icon: '✉️',
        title: 'Email Validation',
        subtitle: 'Verify your email to access the validator',
        content,
        statusBadge: { type: 'pending', text: 'Not Validated' },
        buttons: [
            {
                text: 'Validate Email',
                icon: '📤',
                callback: async (e) => {
                    const button = e.target.closest('button');
                    await sendValidationCode(cardId, button);
                }
            }
        ]
    });

    // Check for stored email
    const storedEmail = localStorage.getItem('validatedEmail');
    if (storedEmail) {
        document.getElementById(`${cardId}-email`).value = storedEmail;
    }

    return card;
}

// Email validation functions
async function sendValidationCode(cardId, button) {
    const emailInput = document.getElementById(`${cardId}-email`);
    const email = emailInput.value.trim();

    // Validate inputs
    if (!validateEmail(email)) {
        showMessage(`${cardId}-messages`, 'Please enter a valid email address', 'error');
        throw new Error('Invalid email');
    }

    globalState.email = email;

    try {
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

    // Update card UI with error checking
    const formEl = document.getElementById(`${cardId}-form`);
    const successEl = document.getElementById(`${cardId}-success`);

    if (formEl) {
        formEl.style.display = 'none';
    } else {
        console.error(`Form element ${cardId}-form not found`);
    }

    if (successEl) {
        successEl.style.display = 'block';
    } else {
        console.error(`Success element ${cardId}-success not found`);
    }

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
