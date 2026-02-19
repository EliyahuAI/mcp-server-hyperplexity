/* ========================================
 * 14c-account-page.js - Account Management UI
 *
 * Card-based account dashboard: balance statement
 * and API key management. Uses the standard card/button
 * design language (createCard, createButtonRow, std-button).
 *
 * Dependencies: 00-config.js, 04-cards.js, 14-account.js
 * ======================================== */

/**
 * Initialize the account card.
 * Appends a standard card to #cardContainer showing balance + transactions.
 * Guard: if card already exists, scroll to it and return.
 */
async function initAccountPage() {
    if (document.getElementById('account-card')) {
        document.getElementById('account-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

    // Messages div is always in the content so openAddCreditsPage can target it immediately
    const loadingHTML = `
        <p style="color:var(--text-secondary);font-size:0.85rem;">Loading account\u2026</p>
        <div id="account-card-messages"></div>
    `;

    createCard({
        id: 'account-card',
        icon: '💳',
        title: 'Account',
        subtitle: escHtml(globalState.email || ''),
        content: loadingHTML,
        buttons: [
            { text: 'API Keys',    icon: '🔑', variant: 'secondary', callback: showApiKeysCard },
            { text: 'Add Credits', icon: '➕', variant: 'primary',   callback: () => openAddCreditsPage(null, 'account-card-messages') },
            { text: 'Sign Out',    icon: '⎋',  variant: 'quinary',   callback: () => handleLogout() }
        ]
    });

    const contentEl = document.querySelector('#account-card .card-content');
    if (!contentEl) return;

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'getAccountBalance',
                email: globalState.email
            })
        });

        const data = await response.json();

        if (!data.success) {
            contentEl.innerHTML = `
                <p style="color:#dc2626;font-size:0.85rem;">Failed to load account: ${escHtml(data.error || 'Unknown error')}</p>
                <div id="account-card-messages"></div>
            `;
            return;
        }

        const accountInfo = data.account_info || {};
        let balance = data.balance
            ?? accountInfo.current_balance
            ?? accountInfo.balance
            ?? 0;
        balance = typeof balance === 'number' ? balance : parseFloat(balance) || 0;
        globalState.accountBalance = balance;

        const transactions = accountInfo.recent_transactions || data.transactions || data.history || [];

        // data-balance attribute lets updateAllBalanceDisplays() auto-update this element
        // after a Squarespace purchase is detected on focus return
        let html = `
            <div class="acct-balance-label">Current Balance</div>
            <div class="acct-balance" data-balance>$${balance.toFixed(2)}</div>
            <div class="acct-divider"></div>
        `;

        if (transactions.length > 0) {
            html += '<ul class="acct-tx-list">';
            transactions.slice(0, 10).forEach(tx => {
                html += renderTransactionRow(tx);
            });
            html += '</ul>';
        } else {
            html += '<p style="font-size:0.82rem;color:var(--text-secondary);">No recent transactions.</p>';
        }

        // Preserve messages div so any in-flight openAddCreditsPage messages survive the content swap
        html += '<div id="account-card-messages" style="margin-top:0.75rem;"></div>';

        contentEl.innerHTML = html;
    } catch (err) {
        console.error('[ACCOUNT] Error loading balance:', err);
        if (contentEl) {
            contentEl.innerHTML = `
                <p style="color:#dc2626;font-size:0.85rem;">Error loading account. Please try again.</p>
                <div id="account-card-messages"></div>
            `;
        }
    }
}

/**
 * Render a single transaction as an HTML list-item string.
 * Phase 2 note: description will eventually include API key last-4 or source tag.
 * @param {Object} tx - Transaction object
 * @returns {string} HTML string for <li class="acct-tx-row">
 */
function renderTransactionRow(tx) {
    const rawDate = tx.timestamp || tx.created_at || tx.date || '';
    const dateStr = rawDate
        ? new Date(rawDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        : '\u2014';
    const desc = escHtml(tx.description || tx.session_id || 'Transaction');
    const amt = parseFloat(tx.amount ?? tx.cost ?? 0);
    const txType = tx.transaction_type || tx.type || '';
    const isDebit = amt < 0 || txType === 'debit' || txType === 'charge' || txType === 'validation';
    const displayAmt = isDebit
        ? `-$${Math.abs(amt).toFixed(2)}`
        : `+$${Math.abs(amt).toFixed(2)}`;
    const amtClass = isDebit ? 'acct-tx-debit' : 'acct-tx-credit';
    return `<li class="acct-tx-row">
        <span class="acct-tx-date">${dateStr}</span>
        <span class="acct-tx-desc">${desc}</span>
        <span class="acct-tx-amount ${amtClass}">${displayAmt}</span>
    </li>`;
}

/**
 * Show the API Keys card (secondary card appended below account card).
 * Guard: if already open, scroll to it.
 */
async function showApiKeysCard() {
    if (document.getElementById('api-keys-card')) {
        document.getElementById('api-keys-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

    const loadingHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">Loading keys\u2026</p>';

    createCard({
        id: 'api-keys-card',
        icon: '🔑',
        title: 'API Keys',
        subtitle: 'Your API access keys',
        content: loadingHTML,
        buttons: [
            { text: 'Add New Key', icon: '\uFF0B', variant: 'primary',   callback: showInlineAddKeyForm },
            { text: 'Done',        icon: '\u2713',  variant: 'secondary', callback: () => {
                const c = document.getElementById('api-keys-card');
                if (c) c.remove();
            }}
        ]
    });

    await refreshApiKeysList();
}

/**
 * Fetch and render the active API keys list into #api-keys-card .card-content.
 */
async function refreshApiKeysList() {
    const contentEl = document.querySelector('#api-keys-card .card-content');
    if (!contentEl) return;

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'listApiKeys',
                email: globalState.email
            })
        });

        const data = await response.json();

        if (!data.success) {
            contentEl.innerHTML = `<p style="color:#dc2626;font-size:0.85rem;">Failed to load keys: ${escHtml(data.error || 'Unknown error')}</p>`;
            return;
        }

        const activeKeys = (data.api_keys || data.keys || []).filter(k => k.is_active);

        if (activeKeys.length === 0) {
            contentEl.innerHTML = '<p style="font-size:0.85rem;color:var(--text-secondary);">No API keys yet.</p>';
            return;
        }

        let html = '<ul class="acct-keys-list">';
        activeKeys.forEach(key => {
            const name   = escHtml(key.key_name   || 'Unnamed Key');
            const prefix = escHtml(key.key_prefix  || 'hpx_???_...');
            html += `<li class="acct-key-row">
                <span class="acct-key-name">${name}</span>
                <span class="acct-key-prefix">${prefix}\u2026</span>
                <button class="std-button danger acct-key-remove"
                        data-prefix="${prefix}"
                        onclick="revokeKeyAndRefresh(this.dataset.prefix)">
                    Remove
                </button>
            </li>`;
        });
        html += '</ul>';

        contentEl.innerHTML = html;
    } catch (err) {
        console.error('[ACCOUNT] Error loading keys:', err);
        if (contentEl) {
            contentEl.innerHTML = '<p style="color:#dc2626;font-size:0.85rem;">Error loading keys. Please try again.</p>';
        }
    }
}

/**
 * Append inline add-key form to the API keys card content.
 * Called from the "Add New Key" button callback.
 */
function showInlineAddKeyForm() {
    const contentEl = document.querySelector('#api-keys-card .card-content');
    if (!contentEl) return;

    // Don't add a second form if one already exists
    if (contentEl.querySelector('.acct-add-key-form')) return;

    contentEl.insertAdjacentHTML('beforeend', `
        <div class="acct-add-key-form" id="acct-add-key-form">
            <input type="text" class="acct-add-key-input" id="acct-new-key-name"
                   placeholder="Key name (e.g. My App)" maxlength="60" autocomplete="off" />
            <button class="std-button primary" onclick="submitNewApiKey()">
                <span class="button-text">Create</span>
            </button>
        </div>
        <div id="acct-add-key-messages" style="font-size:0.82rem;margin-top:0.4rem;color:#dc2626;"></div>
    `);

    const input = document.getElementById('acct-new-key-name');
    if (input) input.focus();
}

/**
 * Submit the inline create-key form.
 * Called from inline onclick — reads #acct-new-key-name directly.
 */
async function submitNewApiKey() {
    const nameInput = document.getElementById('acct-new-key-name');
    const msgEl    = document.getElementById('acct-add-key-messages');
    const keyName  = nameInput ? nameInput.value.trim() : '';

    if (!keyName) {
        if (msgEl) msgEl.textContent = 'Key name is required.';
        if (nameInput) nameInput.focus();
        return;
    }

    const createBtn = document.querySelector('#acct-add-key-form .std-button');
    if (createBtn) {
        createBtn.disabled = true;
        createBtn.querySelector('.button-text').textContent = 'Creating\u2026';
    }
    if (msgEl) msgEl.textContent = '';

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'createApiKey',
                email: globalState.email,
                key_name: keyName,
                tier: 'live',
                scopes: ['validate']
            })
        });

        const data = await response.json();

        if (!data.success) {
            if (msgEl) msgEl.textContent = data.error || 'Failed to create key.';
            if (createBtn) {
                createBtn.disabled = false;
                createBtn.querySelector('.button-text').textContent = 'Create';
            }
            return;
        }

        const rawKey = data.api_key || data.raw_key || data.key || '';

        // Replace the form with the one-time raw key display
        const formEl = document.getElementById('acct-add-key-form');
        if (formEl) formEl.remove();
        if (msgEl) msgEl.remove();

        const contentEl = document.querySelector('#api-keys-card .card-content');
        if (contentEl) {
            contentEl.insertAdjacentHTML('beforeend', `
                <div class="acct-raw-key-box" id="acct-raw-key-box">
                    <code class="acct-raw-key-code" id="acct-raw-key-code">${escHtml(rawKey)}</code>
                    <p class="acct-raw-key-warning">\u26A0 Store this key \u2014 it will not be shown again.</p>
                    <button class="std-button secondary" style="margin-right:0.5rem;" onclick="copyNewApiKey()">
                        <span class="button-text">Copy</span>
                    </button>
                    <button class="std-button primary" onclick="closeRawKeyDisplay()">
                        <span class="button-text">Close</span>
                    </button>
                </div>
            `);
        }
    } catch (err) {
        console.error('[ACCOUNT] Error creating key:', err);
        if (msgEl) msgEl.textContent = 'Network error. Please try again.';
        if (createBtn) {
            createBtn.disabled = false;
            createBtn.querySelector('.button-text').textContent = 'Create';
        }
    }
}

/**
 * Copy the one-time raw API key text to clipboard.
 * Called from inline onclick in the raw key display box.
 */
async function copyNewApiKey() {
    const codeEl = document.getElementById('acct-raw-key-code');
    if (!codeEl) return;

    const text = codeEl.textContent || '';
    try {
        await navigator.clipboard.writeText(text);
    } catch (_) {
        const range = document.createRange();
        range.selectNode(codeEl);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
    }

    const box = document.getElementById('acct-raw-key-box');
    const copyBtn = box ? box.querySelector('.std-button.secondary') : null;
    if (copyBtn) {
        copyBtn.querySelector('.button-text').textContent = 'Copied!';
        setTimeout(() => { copyBtn.querySelector('.button-text').textContent = 'Copy'; }, 2000);
    }
}

/**
 * Close the one-time raw key display and refresh the keys list.
 * Called from inline onclick.
 */
function closeRawKeyDisplay() {
    const box = document.getElementById('acct-raw-key-box');
    if (box) box.remove();
    refreshApiKeysList();
}

/**
 * Inline-confirm then revoke a key, then refresh the keys list.
 * Called from inline onclick on Remove buttons.
 * @param {string} keyPrefix
 */
async function revokeKeyAndRefresh(keyPrefix) {
    if (!confirm(`Revoke key ${keyPrefix}?`)) return;

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'revokeApiKey',
                email: globalState.email,
                key_prefix: keyPrefix
            })
        });

        const data = await response.json();

        if (!data.success) {
            alert(data.error || 'Failed to revoke key.');
            return;
        }

        await refreshApiKeysList();
    } catch (err) {
        console.error('[ACCOUNT] Error revoking key:', err);
        alert('Network error. Please try again.');
    }
}

/**
 * Escape HTML special characters to prevent XSS.
 */
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Expose for 99-init.js and badge click
window.initAccountPage = initAccountPage;
// Expose for inline onclick handlers
window.submitNewApiKey    = submitNewApiKey;
window.copyNewApiKey      = copyNewApiKey;
window.closeRawKeyDisplay = closeRawKeyDisplay;
window.revokeKeyAndRefresh = revokeKeyAndRefresh;
