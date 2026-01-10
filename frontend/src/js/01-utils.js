/* ========================================
 * Utility Functions Module
 * Pure utility functions for formatting, validation, and helpers
 *
 * Dependencies: 00-config.js (globalState)
 * ======================================== */

// ============================================
// ID GENERATION
// ============================================

function generateCardId() {
    return `card-${++globalState.cardCounter}`;
}

// ============================================
// VALIDATION UTILITIES
// ============================================

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ============================================
// FORMATTING UTILITIES
// ============================================

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + ['Bytes', 'KB', 'MB', 'GB'][i];
}

function formatLocalDateTime(dateString) {
    if (!dateString) return 'Unknown';

    try {
        // Handle various date formats from backend
        let date;
        if (typeof dateString === 'string') {
            // Handle ISO strings with or without timezone info
            if (dateString.endsWith('Z') || dateString.includes('+') || dateString.includes('T')) {
                date = new Date(dateString);
            } else {
                // Assume local time if no timezone info
                date = new Date(dateString + 'T00:00:00');
            }
        } else {
            date = new Date(dateString);
        }

        // Verify date is valid
        if (isNaN(date.getTime())) {
            console.warn('Invalid date string:', dateString);
            return 'Invalid date';
        }

        // Use local timezone with date and time
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
            timeZoneName: 'short'
        });
    } catch (e) {
        console.error('Date formatting error for:', dateString, e);
        return 'Invalid date';
    }
}

// ============================================
// COLOR UTILITIES
// ============================================

function getConfidenceColor(confidenceScore) {
    /**
     * Convert confidence score (0-100) to gradient color
     * null/undefined -> green (default until confidence arrives)
     * 0-50: red-yellow gradient
     * 50-100: yellow-green gradient
     */
    if (confidenceScore === null || confidenceScore === undefined) {
        return '#2DFF45'; // Green default
    }

    // Clamp to 0-100 range
    confidenceScore = Math.max(0, Math.min(100, confidenceScore));

    let r, g, b;

    if (confidenceScore <= 50) {
        // Red to Yellow gradient (0-50)
        const t = confidenceScore / 50; // 0 to 1
        r = 255;
        g = Math.round(255 * t); // 0 to 255
        b = 0;
    } else {
        // Yellow to Green gradient (50-100)
        const t = (confidenceScore - 50) / 50; // 0 to 1
        r = Math.round(255 * (1 - t)); // 255 to 0
        g = 255;
        b = Math.round(69 * t); // 0 to 69 (matching #2DFF45)
    }

    return `rgb(${r}, ${g}, ${b})`;
}

// ============================================
// DEBOUNCING UTILITIES
// ============================================

/**
 * Debounce config generation functions to prevent multiple rapid calls
 * @param {string} key - Unique identifier for the debounced function
 * @param {Function} func - Function to debounce
 * @param {number} delay - Delay in milliseconds (default: 2000)
 * @returns {Function} Debounced function
 */
function debounceConfigAction(key, func, delay = 2000) {
    return function(...args) {
        // Check if already processing
        if (globalState.isProcessingConfig) {
            return;
        }

        // Clear existing timer for this key
        if (globalState.debounceTimers.has(key)) {
            clearTimeout(globalState.debounceTimers.get(key));
        }

        // Set new timer
        const timerId = setTimeout(() => {
            globalState.debounceTimers.delete(key);
            globalState.isProcessingConfig = true;

            // Set a safety timeout to reset processing state after 10 minutes
            setTimeout(() => {
                if (globalState.isProcessingConfig) {
                    globalState.isProcessingConfig = false;
                }
            }, 600000); // 10 minutes

            // Execute the function and handle completion
            Promise.resolve(func.apply(this, args))
                .catch(error => {
                    console.error(`Error in ${key}:`, error);
                })
                .finally(() => {
                    globalState.isProcessingConfig = false;
                });
        }, delay);

        globalState.debounceTimers.set(key, timerId);
    };
}

// ============================================
// DISPLAY UTILITIES
// ============================================

function isPortraitMode() {
    // Check if device is in portrait orientation (matches CSS media query)
    return window.innerWidth < 768 && window.matchMedia('(orientation: portrait)').matches;
}

function truncateTickerText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
}

// ============================================
// MESSAGE DISPLAY UTILITY
// ============================================

function showMessage(containerId, message, type = 'info', updateExisting = false, messageId = null) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const icon = type === 'success' ? '✓' : type === 'error' ? '✗' : type === 'warning' ? '⚠' : 'ℹ';

    // Always try to update if messageId is provided
    if (messageId) {
        let existingMessage = container.querySelector(`[data-message-id="${messageId}"]`);

        if (existingMessage) {
            // Update existing message
            existingMessage.className = `message message-${type}`;
            existingMessage.innerHTML = `<span class="message-icon">${icon}</span><span>${message}</span>`;
            return existingMessage;
        }
    }

    // Create new message element
    const messageEl = document.createElement('div');
    messageEl.className = `message message-${type}`;
    messageEl.innerHTML = `<span class="message-icon">${icon}</span><span>${message}</span>`;

    // Add message ID if provided
    if (messageId) {
        messageEl.setAttribute('data-message-id', messageId);
    }

    container.appendChild(messageEl);
    return messageEl;
}
