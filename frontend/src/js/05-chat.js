/* ========================================
 * 05-chat.js - Message Display & Markdown
 *
 * Handles message display, markdown rendering,
 * and final card state management.
 *
 * Dependencies: 00-config.js (globalState)
 * ======================================== */

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

// Helper to show final card state consistently
function showFinalCardState(cardId, message, type = 'success') {
    // Hide all card sections first
    const optionsContainer = document.getElementById(`${cardId}-options`);
    const buttonsContainer = document.getElementById(`${cardId}-buttons`);
    const configList = document.getElementById(`${cardId}-config-list`);
    const matchingInfoContainer = document.getElementById(`${cardId}-matching-info`);

    if (optionsContainer) optionsContainer.style.display = 'none';
    if (buttonsContainer) buttonsContainer.style.display = 'none';
    if (configList) configList.style.display = 'none';
    if (matchingInfoContainer) matchingInfoContainer.style.display = 'none';

    // Show only the message
    const messagesContainer = document.getElementById(`${cardId}-messages`);
    if (messagesContainer) {
        messagesContainer.innerHTML = '';
        showMessage(`${cardId}-messages`, message, type);
    }
}

// Show upload requirements info
function showUploadInfo() {
    const infoMessage = `
        <strong>Upload Requirements:</strong><br>
        • Excel (.xlsx) or CSV (.csv) files accepted<br>
        • If Excel, table should be on the first worksheet<br>
        • Information should be available on the internet<br>
        • Row values cannot reference other rows<br>
        • Descriptive columns are really helpful for better research results
    `;

    // Create a temporary modal-like overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.5); z-index: 10000; display: flex;
        align-items: center; justify-content: center;
    `;

    const modal = document.createElement('div');
    modal.style.cssText = `
        background: white; padding: 24px; border-radius: 8px;
        max-width: 500px; margin: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    `;

    modal.innerHTML = `
        <div style="margin-bottom: 16px;">${infoMessage}</div>
        <button id="info-got-it-btn"
                style="background: #2d5a27; color: white; border: none; padding: 8px 16px;
                       border-radius: 4px; cursor: pointer;">Got it</button>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Close on button click
    modal.querySelector('#info-got-it-btn').addEventListener('click', () => {
        overlay.remove();
    });

    // Close on backdrop click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });
}

// Make showUploadInfo globally accessible
window.showUploadInfo = showUploadInfo;

// Markdown rendering wrapper
function renderMarkdown(text) {
    if (!text) return '';

    marked.setOptions({
        breaks: true,
        gfm: true,
        sanitize: false,
        smartLists: true,
        smartypants: false
    });

    let html = marked.parse(text);

    // Handle Unicode escapes
    html = html.replace(/\\u([0-9a-fA-F]{4})/g, (match, hexCode) => {
        return String.fromCharCode(parseInt(hexCode, 16));
    });

    return `<div class="markdown-content">${html}</div>`;
}
