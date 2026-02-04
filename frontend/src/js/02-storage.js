/* ========================================
 * Storage Module
 * localStorage management for session and user data
 *
 * Dependencies: 00-config.js (globalState)
 * ======================================== */

// ============================================
// SESSION STORAGE
// ============================================

function saveSessionId(sessionId) {
    try {
        localStorage.setItem('sessionId', sessionId);
        globalState.sessionId = sessionId;
    } catch (e) {
        console.error('[STORAGE] Error saving session ID:', e);
    }
}

function getSessionId() {
    try {
        return localStorage.getItem('sessionId');
    } catch (e) {
        console.error('[STORAGE] Error getting session ID:', e);
        return null;
    }
}

function removeSessionId() {
    try {
        localStorage.removeItem('sessionId');
        globalState.sessionId = null;
    } catch (e) {
        console.error('[STORAGE] Error removing session ID:', e);
    }
}

// ============================================
// EMAIL STORAGE
// ============================================

function saveValidatedEmail(email) {
    try {
        // SECURITY: Store in sessionStorage (not localStorage) to prevent attacks
        // sessionStorage clears on browser close = natural logout
        // localStorage persists forever = attacker can modify email and get victim's token
        sessionStorage.setItem('validatedEmail', email);
        globalState.email = email;
    } catch (e) {
        console.error('[STORAGE] Error saving email:', e);
    }
}

function getValidatedEmail() {
    try {
        return sessionStorage.getItem('validatedEmail');
    } catch (e) {
        console.error('[STORAGE] Error getting email:', e);
        return null;
    }
}

function removeValidatedEmail() {
    try {
        sessionStorage.removeItem('validatedEmail');
        globalState.email = '';
    } catch (e) {
        console.error('[STORAGE] Error removing email:', e);
    }
}

// ============================================
// COMBINED UTILITIES
// ============================================

function getCurrentUserEmail() {
    // Try to get email from various possible sources
    const emailInputs = document.querySelectorAll('input[type="email"]');
    for (const input of emailInputs) {
        if (input.value && input.value.includes('@')) {
            return input.value;
        }
    }

    // Try stored email
    const storedEmail = getValidatedEmail();
    if (storedEmail && storedEmail.includes('@')) {
        return storedEmail;
    }

    return null;
}

function clearSessionData() {
    removeSessionId();
    removeValidatedEmail();
}
