/* ========================================
 * 14c-account-page.js - Account Management UI
 *
 * Card-based account dashboard: balance, activity history,
 * add credits, and API key management.
 * Uses the standard card/button design language
 * (createCard, createButtonRow, std-button).
 *
 * Dependencies: 00-config.js, 04-cards.js, 14-account.js
 * ======================================== */

/**
 * Initialize the account card.
 * Shows balance and navigation buttons.
 * Guard: if card already exists, scroll to it and return.
 */
async function initAccountPage() {
    if (document.getElementById('account-card')) {
        document.getElementById('account-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

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
            { text: 'Add Credits', icon: '⚡', variant: 'primary',   callback: showAddCreditsCard },
            { text: 'Activity',    icon: '📊', variant: 'tertiary',  callback: showActivityCard },
            { text: 'API Keys',    icon: '🔑', variant: 'secondary', callback: showApiKeysCard },
            { text: 'Sign Out',    icon: '⎋',  variant: 'quinary',   callback: () => handleLogout() },
            { text: 'Close',       icon: '✕',  variant: 'secondary', callback: () => {
                const c = document.getElementById('account-card');
                if (c) c.remove();
            }}
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

        // Cache for Activity card to avoid a second fetch
        globalState._cachedTransactions = accountInfo.recent_transactions
            || data.transactions
            || data.history
            || [];

        // data-balance attribute lets updateAllBalanceDisplays() auto-update on purchase
        contentEl.innerHTML = `
            <div class="acct-balance-label">Current Balance</div>
            <div class="acct-balance" data-balance>$${balance.toFixed(2)}</div>
            <div id="account-card-messages" style="margin-top:0.75rem;"></div>
        `;
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
 * Show the Activity card with all recent transactions in a scrollable list.
 * Guard: if already open, scroll to it.
 */
async function showActivityCard() {
    if (document.getElementById('activity-card')) {
        document.getElementById('activity-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

    createCard({
        id: 'activity-card',
        icon: '📊',
        title: 'Activity',
        subtitle: 'Recent transactions',
        content: '<p style="color:var(--text-secondary);font-size:0.85rem;">Loading\u2026</p>',
        buttons: [
            { text: 'Done', icon: '\u2713', variant: 'secondary', callback: () => {
                const c = document.getElementById('activity-card');
                if (c) c.remove();
            }}
        ]
    });

    const contentEl = document.querySelector('#activity-card .card-content');
    if (!contentEl) return;

    try {
        // Always fetch full transaction history (up to 100) — do not use the 10-row cache
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'getAccountBalance',
                email: globalState.email,
                transaction_limit: 100
            })
        });
        const data = await response.json();
        if (!data.success) {
            contentEl.innerHTML = `<p style="color:#dc2626;font-size:0.85rem;">Failed to load activity.</p>`;
            return;
        }
        const accountInfo = data.account_info || {};
        const transactions = accountInfo.recent_transactions || data.transactions || data.history || [];

        if (transactions.length === 0) {
            contentEl.innerHTML = '<p style="font-size:0.85rem;color:var(--text-secondary);">No transactions yet.</p>';
            return;
        }

        let html = '<div class="acct-activity-scroll"><ul class="acct-tx-list">';
        transactions.forEach(tx => { html += renderTransactionRow(tx); });
        html += '</ul></div>';
        contentEl.innerHTML = html;
    } catch (err) {
        console.error('[ACCOUNT] Error loading activity:', err);
        if (contentEl) {
            contentEl.innerHTML = '<p style="color:#dc2626;font-size:0.85rem;">Error loading activity. Please try again.</p>';
        }
    }
}

/**
 * Show the Add Credits card (new card below account card).
 * Includes preset chips, custom input, and a cost estimator.
 * Guard: if already open, scroll to it.
 */
function showAddCreditsCard() {
    if (document.getElementById('add-credits-card')) {
        document.getElementById('add-credits-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

    createCard({
        id: 'add-credits-card',
        icon: '⚡',
        title: 'Add Credits',
        subtitle: 'Choose an amount to add',
        content: `
            <div class="acct-credits-inner">
                <p class="acct-credits-label">How many credits would you like to add?</p>
                <div class="acct-credits-presets">
                    <button class="acct-credit-chip" onclick="selectCreditsAmount(10)">$10</button>
                    <button class="acct-credit-chip" onclick="selectCreditsAmount(25)">$25</button>
                    <button class="acct-credit-chip" onclick="selectCreditsAmount(50)">$50</button>
                    <button class="acct-credit-chip" onclick="selectCreditsAmount(100)">$100</button>
                </div>
                <div class="acct-credits-custom">
                    <span class="acct-credits-currency">$</span>
                    <input type="number" id="acct-credits-amount" class="acct-add-key-input acct-credits-custom-input"
                           placeholder="Custom" min="1" max="10000" step="1"
                           onkeydown="if(event.key==='Enter') purchaseCreditsAmount()" />
                </div>

                <div class="acct-est-divider"></div>

                <p class="acct-credits-label">Not sure how much you need?</p>
                <div class="acct-est-fields">
                    <label class="acct-est-field">
                        <span class="acct-est-field-label">Rows</span>
                        <input type="number" id="acct-est-rows" class="acct-add-key-input acct-est-input"
                               value="40" min="1" max="1000000" oninput="estimateCreditNeed()" />
                    </label>
                    <label class="acct-est-field">
                        <span class="acct-est-field-label">Columns</span>
                        <input type="number" id="acct-est-cols" class="acct-add-key-input acct-est-input"
                               value="5" min="1" max="500" oninput="estimateCreditNeed()" />
                    </label>
                    <label class="acct-est-field">
                        <span class="acct-est-field-label">Validations</span>
                        <input type="number" id="acct-est-validations" class="acct-add-key-input acct-est-input"
                               value="2" min="1" max="100" oninput="estimateCreditNeed()" />
                    </label>
                </div>
                <div id="acct-est-result" class="acct-est-result"></div>
                <div id="add-credits-card-messages" style="margin-top:0.5rem;"></div>
            </div>
        `,
        buttons: [
            { text: 'Buy Credits', icon: '\u2795', variant: 'primary',   callback: purchaseCreditsAmount },
            { text: 'Cancel',      icon: '\u00D7', variant: 'secondary', callback: () => {
                const c = document.getElementById('add-credits-card');
                if (c) c.remove();
            }}
        ]
    });

    // Show initial estimate and focus custom input after card renders
    setTimeout(() => {
        estimateCreditNeed();
        document.getElementById('acct-credits-amount')?.focus();
    }, 150);
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

    createCard({
        id: 'api-keys-card',
        icon: '🔑',
        title: 'API Keys',
        subtitle: 'Your API access keys',
        content: '<p style="color:var(--text-secondary);font-size:0.85rem;">Loading keys\u2026</p>',
        buttons: [
            { text: 'Add New Key', icon: '\u002B', variant: 'primary',   callback: showInlineAddKeyForm },
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
            contentEl.innerHTML = '<p style="font-size:0.85rem;color:var(--text-secondary);">No API keys yet. Click \u201CAdd New Key\u201D to create one.</p>';
            return;
        }

        let html = '<ul class="acct-keys-list">';
        activeKeys.forEach(key => {
            const name   = escHtml(key.key_name  || 'Unnamed Key');
            const prefix = escHtml(key.key_prefix || 'hpx_???_...');
            html += `<li class="acct-key-row">
                <span class="acct-key-name">${name}</span>
                <span class="acct-key-prefix">${prefix}\u2026</span>
                <button class="std-button danger acct-key-remove"
                        data-prefix="${prefix}"
                        onclick="revokeKeyAndRefresh(this.dataset.prefix)">
                    <span class="button-text">Remove</span>
                    <span class="spinner"></span>
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
 * Uses createButtonRow so button heights match card buttons exactly.
 */
function showInlineAddKeyForm() {
    const contentEl = document.querySelector('#api-keys-card .card-content');
    if (!contentEl) return;
    if (contentEl.querySelector('.acct-add-key-form')) return;

    contentEl.insertAdjacentHTML('beforeend', `
        <div class="acct-add-key-form" id="acct-add-key-form">
            <input type="text" class="acct-add-key-input" id="acct-new-key-name"
                   placeholder="Key name (e.g. My App)" maxlength="60" autocomplete="off" />
        </div>
        <p id="acct-add-key-messages" class="acct-form-msg"></p>
        <div id="acct-key-create-buttons"></div>
    `);

    createButtonRow('acct-key-create-buttons', [
        { text: 'Create Key', icon: '\u2713', variant: 'primary',   callback: submitNewApiKey },
        { text: 'Cancel',     icon: '\u00D7', variant: 'secondary', callback: () => {
            ['acct-add-key-form', 'acct-add-key-messages', 'acct-key-create-buttons'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.remove();
            });
        }}
    ]);

    const input = document.getElementById('acct-new-key-name');
    if (input) {
        input.focus();
        input.addEventListener('keydown', e => { if (e.key === 'Enter') submitNewApiKey(); });
    }
}

/**
 * Submit the inline create-key form.
 * Called as a createButtonRow callback — reads #acct-new-key-name directly.
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
    if (msgEl) msgEl.textContent = '';

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
        return;
    }

    const rawKey = data.api_key || data.raw_key || data.key || '';

    // Remove form + buttons before showing the one-time key
    ['acct-add-key-form', 'acct-add-key-messages', 'acct-key-create-buttons'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
    });

    const contentEl = document.querySelector('#api-keys-card .card-content');
    if (contentEl) {
        contentEl.insertAdjacentHTML('beforeend', `
            <div class="acct-raw-key-box" id="acct-raw-key-box">
                <code class="acct-raw-key-code" id="acct-raw-key-code">${escHtml(rawKey)}</code>
                <p class="acct-raw-key-warning">\u26A0 Store this key \u2014 it will not be shown again.</p>
                <div id="acct-raw-key-buttons"></div>
            </div>
        `);
        createButtonRow('acct-raw-key-buttons', [
            { text: 'Copy Key', icon: '📋', variant: 'secondary', callback: copyNewApiKey },
            { text: 'Done',     icon: '\u2713', variant: 'primary', callback: closeRawKeyDisplay }
        ]);
    }
}

/**
 * Copy the one-time raw API key text to clipboard.
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

    // Brief visual feedback on the Copy button text
    const box = document.getElementById('acct-raw-key-box');
    const btn = box ? box.querySelector('.std-button.secondary .button-text') : null;
    if (btn) {
        btn.textContent = '📋 Copied!';
        setTimeout(() => { btn.textContent = '📋 Copy Key'; }, 2000);
    }
}

/**
 * Close the one-time raw key display and refresh the keys list.
 */
function closeRawKeyDisplay() {
    const box = document.getElementById('acct-raw-key-box');
    if (box) box.remove();
    refreshApiKeysList();
}

/**
 * Inline-confirm then revoke a key, then refresh the keys list.
 * @param {string} keyPrefix
 */
async function revokeKeyAndRefresh(keyPrefix) {
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

// ============================================================
// ADD CREDITS
// ============================================================

/**
 * Called by preset chip onclick — launches the purchase flow immediately.
 * @param {number} amount - Dollar amount of credits to add
 */
function selectCreditsAmount(amount) {
    const msgId = document.getElementById('add-credits-card-messages')
        ? 'add-credits-card-messages'
        : 'account-card-messages';
    openAddCreditsPage(amount, msgId);
}

/**
 * Called by the "Buy Credits" card button — validates the custom input then launches.
 */
function purchaseCreditsAmount() {
    const input = document.getElementById('acct-credits-amount');
    const amount = input ? parseInt(input.value, 10) : 0;
    if (!amount || amount < 1) {
        if (input) {
            input.style.borderColor = '#dc2626';
            input.focus();
            setTimeout(() => { input.style.borderColor = ''; }, 1500);
        }
        return;
    }
    const msgId = document.getElementById('add-credits-card-messages')
        ? 'add-credits-card-messages'
        : 'account-card-messages';
    openAddCreditsPage(amount, msgId);
}

// ============================================================
// COST ESTIMATOR
// ============================================================

/**
 * Calculate estimated credit need from rows × columns × validations × $0.05,
 * add 20% buffer, round up to nearest dollar, minimum $2.
 * Populates #acct-est-result with the result and a "Use" button.
 */
function estimateCreditNeed() {
    const rows = parseInt(document.getElementById('acct-est-rows')?.value, 10) || 0;
    const cols = parseInt(document.getElementById('acct-est-cols')?.value, 10) || 0;
    const vals = parseInt(document.getElementById('acct-est-validations')?.value, 10) || 0;
    const resultEl = document.getElementById('acct-est-result');
    if (!resultEl) return;

    if (!rows || !cols || !vals) {
        resultEl.innerHTML = '';
        return;
    }

    const base     = rows * cols * vals * 0.05;
    const estimate = Math.max(2, Math.ceil(base * 1.2));

    resultEl.innerHTML = `
        <div class="acct-est-result-row">
            <span class="acct-est-result-label">Estimated cost:</span>
            <span class="acct-est-amount">~$${estimate}</span>
            <button class="acct-credit-chip" onclick="useEstimatedAmount(${estimate})">Use $${estimate}</button>
        </div>
        <p class="acct-est-breakdown">
            $0.05 &times; ${rows.toLocaleString()} rows &times; ${cols} cols &times; ${vals} validation${vals !== 1 ? 's' : ''} + 20% buffer
        </p>
    `;
}

/**
 * Pre-fill the custom credit amount input with the estimated value.
 * @param {number} amount
 */
function useEstimatedAmount(amount) {
    const input = document.getElementById('acct-credits-amount');
    if (input) {
        input.value = amount;
        input.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        input.focus();
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
window.submitNewApiKey       = submitNewApiKey;
window.copyNewApiKey         = copyNewApiKey;
window.closeRawKeyDisplay    = closeRawKeyDisplay;
window.revokeKeyAndRefresh   = revokeKeyAndRefresh;
window.selectCreditsAmount   = selectCreditsAmount;
window.purchaseCreditsAmount = purchaseCreditsAmount;
window.showAddCreditsCard    = showAddCreditsCard;
window.showActivityCard      = showActivityCard;
window.estimateCreditNeed    = estimateCreditNeed;
window.useEstimatedAmount    = useEstimatedAmount;
