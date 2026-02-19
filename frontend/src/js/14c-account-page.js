/* ========================================
 * 14c-account-page.js - Account Management UI
 *
 * Full account management dashboard: API key CRUD,
 * balance display, and usage history.
 * Rendered when URL path contains /account.
 *
 * Dependencies: 00-config.js, 05-chat.js, 14-account.js
 * ======================================== */

/**
 * Initialize the account management page.
 * Replaces the card container with the account dashboard.
 */
async function initAccountPage() {
    const cardContainer = document.getElementById('cardContainer');
    if (!cardContainer) return;

    cardContainer.innerHTML = `
        <div class="account-page" id="account-page">
            <div class="account-header">
                <h1 class="account-title">Account Management</h1>
                <a href="/" class="account-back-link">&#8592; Back to Hyperplexity</a>
            </div>

            <!-- Account Overview -->
            <div class="account-section" id="account-overview-section">
                <div class="account-section-header">
                    <h2>Account Overview</h2>
                </div>
                <div class="account-section-body" id="account-overview-body">
                    <div class="account-loading">Loading account info...</div>
                </div>
            </div>

            <!-- API Keys -->
            <div class="account-section" id="account-keys-section">
                <div class="account-section-header">
                    <h2>API Keys</h2>
                    <button class="std-button primary account-create-key-btn" onclick="showCreateApiKeyModal()">
                        <span class="button-text">+ New API Key</span>
                    </button>
                </div>
                <div class="account-section-body" id="account-keys-body">
                    <div class="account-loading">Loading API keys...</div>
                </div>
            </div>

            <!-- Usage & Billing -->
            <div class="account-section" id="account-usage-section">
                <div class="account-section-header">
                    <h2>Usage &amp; Billing</h2>
                </div>
                <div class="account-section-body" id="account-usage-body">
                    <div class="account-loading">Loading usage history...</div>
                </div>
            </div>
        </div>
    `;

    // Load all sections in parallel
    await Promise.all([
        loadAccountOverview(),
        loadApiKeys(),
        loadUsageHistory()
    ]);
}

/**
 * Load account balance and overview info.
 */
async function loadAccountOverview() {
    const body = document.getElementById('account-overview-body');
    if (!body) return;

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
            body.innerHTML = `<div class="account-error">Failed to load account info: ${accountEscapeHtml(data.error || 'Unknown error')}</div>`;
            return;
        }

        let balance = data.balance;
        if (balance === undefined && data.account_info) {
            balance = data.account_info.balance || data.account_info.current_balance || 0;
        }
        balance = typeof balance === 'number' ? balance : parseFloat(balance) || 0;
        globalState.accountBalance = balance;

        body.innerHTML = `
            <div class="account-overview-grid">
                <div class="account-stat">
                    <div class="account-stat-label">Current Balance</div>
                    <div class="account-stat-value account-balance-display">$${balance.toFixed(2)}</div>
                </div>
                <div class="account-stat">
                    <div class="account-stat-label">Email</div>
                    <div class="account-stat-value">${accountEscapeHtml(globalState.email)}</div>
                </div>
                <div class="account-stat">
                    <div class="account-stat-label">Account Status</div>
                    <div class="account-stat-value account-status-active">Active</div>
                </div>
            </div>
            <div class="account-recharge-area">
                <button class="std-button secondary" onclick="openAddCreditsPage(null, 'account-overview-messages')">
                    <span class="button-text">Recharge Account</span>
                </button>
                <div id="account-overview-messages" style="margin-top: 8px;"></div>
            </div>
        `;
    } catch (error) {
        console.error('[ACCOUNT] Error loading overview:', error);
        body.innerHTML = `<div class="account-error">Error loading account info. Please refresh the page.</div>`;
    }
}

/**
 * Load and render the API keys list.
 */
async function loadApiKeys() {
    const body = document.getElementById('account-keys-body');
    if (!body) return;

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
            body.innerHTML = `<div class="account-error">Failed to load API keys: ${accountEscapeHtml(data.error || 'Unknown error')}</div>`;
            return;
        }

        const keys = data.keys || [];

        if (keys.length === 0) {
            body.innerHTML = `
                <div class="account-empty">
                    <p>No API keys yet. Create your first key to access the Hyperplexity API programmatically.</p>
                </div>
            `;
            return;
        }

        const activeKeys = keys.filter(k => k.is_active);
        const revokedKeys = keys.filter(k => !k.is_active);

        let html = activeKeys.map(key => renderApiKeyCard(key, true)).join('');

        if (revokedKeys.length > 0) {
            html += `<div class="account-revoked-section"><h3>Revoked Keys</h3>`;
            html += revokedKeys.map(key => renderApiKeyCard(key, false)).join('');
            html += `</div>`;
        }

        body.innerHTML = html;
    } catch (error) {
        console.error('[ACCOUNT] Error loading API keys:', error);
        body.innerHTML = `<div class="account-error">Error loading API keys. Please refresh the page.</div>`;
    }
}

/**
 * Render a single API key card.
 */
function renderApiKeyCard(key, isActive) {
    const createdDate = key.created_at ? new Date(key.created_at).toLocaleDateString() : 'Unknown';
    const lastUsed = key.last_used_at ? accountFormatRelativeTime(key.last_used_at) : 'Never';
    const tierBadgeClass = key.tier === 'live' ? 'account-badge-live'
        : key.tier === 'test' ? 'account-badge-test' : 'account-badge-int';
    const scopes = (key.scopes || []).join(', ') || 'none';
    const keyPrefix = accountEscapeHtml(key.key_prefix || 'hpx_???_...');
    const keyName = accountEscapeHtml(key.key_name || 'Unnamed Key');

    if (!isActive) {
        const revokedDate = key.revoked_at ? new Date(key.revoked_at).toLocaleDateString() : 'Unknown';
        return `
            <div class="account-key-card account-key-revoked">
                <div class="account-key-header">
                    <div class="account-key-status-indicator account-key-status-revoked">Revoked</div>
                </div>
                <div class="account-key-name">${keyName}</div>
                <div class="account-key-prefix account-key-prefix-mono">${keyPrefix}...</div>
                <div class="account-key-meta">
                    <span>Revoked: ${revokedDate}</span>
                    ${key.revoked_reason ? `<span>Reason: ${accountEscapeHtml(key.revoked_reason)}</span>` : ''}
                </div>
            </div>
        `;
    }

    return `
        <div class="account-key-card">
            <div class="account-key-header">
                <div class="account-key-status-indicator account-key-status-active">Active</div>
                <span class="account-badge ${tierBadgeClass}">${accountEscapeHtml(key.tier || 'live')}</span>
            </div>
            <div class="account-key-name">${keyName}</div>
            <div class="account-key-prefix account-key-prefix-mono">${keyPrefix}...</div>
            <div class="account-key-meta">
                <span>Created: ${createdDate}</span>
                <span>Last used: ${lastUsed}</span>
                <span>Scopes: ${accountEscapeHtml(scopes)}</span>
            </div>
            <div class="account-key-actions">
                <button class="std-button secondary account-key-btn"
                        data-key-prefix="${keyPrefix}"
                        data-key-name="${keyName}"
                        onclick="showRevokeKeyModal(this.dataset.keyPrefix, this.dataset.keyName)">
                    Revoke
                </button>
            </div>
        </div>
    `;
}

/**
 * Load and render usage and billing history.
 */
async function loadUsageHistory() {
    const body = document.getElementById('account-usage-body');
    if (!body) return;

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'getUserStats',
                email: globalState.email
            })
        });

        const data = await response.json();

        if (!data.success) {
            body.innerHTML = `<div class="account-error">Failed to load usage history.</div>`;
            return;
        }

        const stats = data.stats || data.data || {};
        const history = data.history || data.validations || data.transactions || [];

        let statsHtml = '';
        const hasStats = stats.total_validations !== undefined || stats.total_spent !== undefined;
        if (hasStats) {
            statsHtml = `<div class="account-overview-grid" style="margin-bottom: 20px;">`;
            if (stats.total_validations !== undefined) {
                statsHtml += `
                    <div class="account-stat">
                        <div class="account-stat-label">Total Validations</div>
                        <div class="account-stat-value">${stats.total_validations || 0}</div>
                    </div>`;
            }
            if (stats.total_spent !== undefined) {
                statsHtml += `
                    <div class="account-stat">
                        <div class="account-stat-label">Total Spent</div>
                        <div class="account-stat-value">$${(stats.total_spent || 0).toFixed(2)}</div>
                    </div>`;
            }
            if (stats.total_rows_processed !== undefined) {
                statsHtml += `
                    <div class="account-stat">
                        <div class="account-stat-label">Rows Processed</div>
                        <div class="account-stat-value">${(stats.total_rows_processed || 0).toLocaleString()}</div>
                    </div>`;
            }
            statsHtml += `</div>`;
        }

        let historyHtml = '';
        if (history.length > 0) {
            historyHtml = `
                <h3 style="margin-bottom: 12px; font-size: 14px; font-weight: 600; color: #555;">Recent Activity</h3>
                <div class="account-history-table">
                    <div class="account-history-header">
                        <span>Date</span>
                        <span>Description</span>
                        <span>Amount</span>
                        <span>Status</span>
                    </div>
                    ${history.slice(0, 20).map(item => {
                        const dateStr = (item.timestamp || item.created_at)
                            ? new Date(item.timestamp || item.created_at).toLocaleDateString()
                            : '-';
                        const desc = accountEscapeHtml(item.description || item.session_id || 'Validation');
                        const amt = parseFloat(item.amount ?? item.cost ?? 0);
                        const status = accountEscapeHtml(item.status || 'completed');
                        const amtClass = amt < 0 ? 'account-amount-debit' : 'account-amount-credit';
                        const amtSign = amt < 0 ? '-' : '+';
                        return `
                            <div class="account-history-row">
                                <span>${dateStr}</span>
                                <span>${desc}</span>
                                <span class="${amtClass}">${amtSign}$${Math.abs(amt).toFixed(2)}</span>
                                <span>${status}</span>
                            </div>`;
                    }).join('')}
                </div>
            `;
        } else {
            historyHtml = `<p style="color: #666; font-size: 14px;">No recent activity found.</p>`;
        }

        body.innerHTML = statsHtml + historyHtml;
    } catch (error) {
        console.error('[ACCOUNT] Error loading usage history:', error);
        body.innerHTML = `<div class="account-error">Error loading usage history. Please refresh the page.</div>`;
    }
}

// ============================================================
// MODAL: Create API Key
// ============================================================

/**
 * Show the Create API Key modal.
 */
function showCreateApiKeyModal() {
    if (document.getElementById('create-key-modal-overlay')) return;
    const overlay = document.createElement('div');
    overlay.className = 'account-modal-overlay';
    overlay.id = 'create-key-modal-overlay';

    overlay.innerHTML = `
        <div class="account-modal" role="dialog" aria-modal="true" aria-labelledby="create-key-modal-title">
            <div class="account-modal-header">
                <h2 class="account-modal-title" id="create-key-modal-title">Create API Key</h2>
                <button class="account-modal-close" onclick="closeAccountModal('create-key-modal-overlay')" aria-label="Close">&#215;</button>
            </div>
            <div class="account-modal-body">
                <div class="account-form-group">
                    <label class="account-form-label" for="key-name-input">
                        Key Name <span class="account-required">*</span>
                    </label>
                    <input type="text" id="key-name-input" class="account-form-input"
                           placeholder="e.g. Production API Key" maxlength="100" autocomplete="off" />
                </div>
                <div class="account-form-group">
                    <label class="account-form-label" for="key-tier-select">Tier</label>
                    <select id="key-tier-select" class="account-form-input">
                        <option value="live">Live (Production)</option>
                        <option value="test">Test (Sandbox)</option>
                    </select>
                </div>
                <div class="account-form-group">
                    <label class="account-form-label">Scopes</label>
                    <div class="account-scopes-grid">
                        <label class="account-scope-item">
                            <input type="checkbox" id="scope-validate" value="validate" checked />
                            <span><strong>validate</strong> &mdash; Submit and manage validation jobs</span>
                        </label>
                        <label class="account-scope-item">
                            <input type="checkbox" id="scope-account-read" value="account:read" />
                            <span><strong>account:read</strong> &mdash; View balance and usage history</span>
                        </label>
                        <label class="account-scope-item">
                            <input type="checkbox" id="scope-config" value="config" />
                            <span><strong>config</strong> &mdash; Access validation configurations</span>
                        </label>
                    </div>
                </div>
                <div id="create-key-error" class="account-form-error" style="display:none;"></div>
            </div>
            <div class="account-modal-footer">
                <button class="std-button secondary" onclick="closeAccountModal('create-key-modal-overlay')">
                    <span class="button-text">Cancel</span>
                </button>
                <button class="std-button primary" id="create-key-submit-btn" onclick="submitCreateApiKey()">
                    <span class="button-text">Create Key</span>
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    // Close on backdrop click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeAccountModal('create-key-modal-overlay');
    });

    // Focus the name input
    setTimeout(() => {
        const input = document.getElementById('key-name-input');
        if (input) input.focus();
    }, 50);
}

/**
 * Submit the Create API Key form.
 */
async function submitCreateApiKey() {
    const nameInput = document.getElementById('key-name-input');
    const tierSelect = document.getElementById('key-tier-select');
    const errorEl = document.getElementById('create-key-error');
    const submitBtn = document.getElementById('create-key-submit-btn');

    const keyName = nameInput ? nameInput.value.trim() : '';
    const tier = tierSelect ? tierSelect.value : 'live';

    if (!keyName) {
        if (errorEl) { errorEl.textContent = 'Key name is required.'; errorEl.style.display = 'block'; }
        if (nameInput) nameInput.focus();
        return;
    }

    const scopes = [];
    [
        { id: 'scope-validate', value: 'validate' },
        { id: 'scope-account-read', value: 'account:read' },
        { id: 'scope-config', value: 'config' }
    ].forEach(({ id, value }) => {
        const cb = document.getElementById(id);
        if (cb && cb.checked) scopes.push(value);
    });

    if (scopes.length === 0) {
        if (errorEl) { errorEl.textContent = 'Please select at least one scope.'; errorEl.style.display = 'block'; }
        return;
    }

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.querySelector('.button-text').textContent = 'Creating...';
    }
    if (errorEl) errorEl.style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'createApiKey',
                email: globalState.email,
                key_name: keyName,
                tier: tier,
                scopes: scopes
            })
        });

        const data = await response.json();

        if (!data.success) {
            const errMsg = data.error || 'Failed to create API key.';
            if (errorEl) { errorEl.textContent = errMsg; errorEl.style.display = 'block'; }
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.querySelector('.button-text').textContent = 'Create Key';
            }
            return;
        }

        closeAccountModal('create-key-modal-overlay');

        const rawKey = data.api_key || data.raw_key || data.key || '';
        showRawKeyModal(rawKey, keyName);

        // Refresh the keys list
        loadApiKeys();
    } catch (error) {
        console.error('[ACCOUNT] Error creating API key:', error);
        if (errorEl) { errorEl.textContent = 'Network error. Please try again.'; errorEl.style.display = 'block'; }
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.querySelector('.button-text').textContent = 'Create Key';
        }
    }
}

// ============================================================
// MODAL: Show Raw Key (one-time display)
// ============================================================

/**
 * Show the raw API key — displayed exactly once after creation.
 */
function showRawKeyModal(rawKey, keyName) {
    const overlay = document.createElement('div');
    overlay.className = 'account-modal-overlay';
    overlay.id = 'raw-key-modal-overlay';

    overlay.innerHTML = `
        <div class="account-modal" role="dialog" aria-modal="true" aria-labelledby="raw-key-modal-title">
            <div class="account-modal-header">
                <h2 class="account-modal-title" id="raw-key-modal-title">Your New API Key</h2>
            </div>
            <div class="account-modal-body">
                <div class="account-key-reveal-warning">
                    &#9888; This key will only be shown <strong>once</strong>. Copy it now and store it securely.
                </div>
                <div class="account-key-name-label" style="margin-bottom: 12px;">
                    Key: <strong>${accountEscapeHtml(keyName)}</strong>
                </div>
                <div class="account-raw-key-display">
                    <code class="account-raw-key-code" id="raw-key-code">${accountEscapeHtml(rawKey)}</code>
                    <button class="account-copy-btn" onclick="copyRawApiKey()" id="copy-key-btn" title="Copy to clipboard">
                        Copy
                    </button>
                </div>
                <div id="copy-key-feedback" class="account-copy-feedback" style="display:none;">
                    &#10003; Copied to clipboard!
                </div>
            </div>
            <div class="account-modal-footer">
                <button class="std-button primary" onclick="closeAccountModal('raw-key-modal-overlay')">
                    <span class="button-text">I've saved my key</span>
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);
}

/**
 * Copy the raw API key text to clipboard.
 */
async function copyRawApiKey() {
    const codeEl = document.getElementById('raw-key-code');
    const feedbackEl = document.getElementById('copy-key-feedback');
    const copyBtn = document.getElementById('copy-key-btn');
    if (!codeEl) return;

    const text = codeEl.textContent || '';
    try {
        await navigator.clipboard.writeText(text);
    } catch (_) {
        // Fallback for older browsers
        const range = document.createRange();
        range.selectNode(codeEl);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
    }

    if (feedbackEl) feedbackEl.style.display = 'block';
    if (copyBtn) copyBtn.textContent = 'Copied!';
    setTimeout(() => {
        if (feedbackEl) feedbackEl.style.display = 'none';
        if (copyBtn) copyBtn.textContent = 'Copy';
    }, 2500);
}

// ============================================================
// MODAL: Revoke Key
// ============================================================

/**
 * Show the Revoke Key confirmation modal.
 */
function showRevokeKeyModal(keyPrefix, keyName) {
    if (document.getElementById('revoke-key-modal-overlay')) return;
    const overlay = document.createElement('div');
    overlay.className = 'account-modal-overlay';
    overlay.id = 'revoke-key-modal-overlay';

    // Embed key info as data attributes to avoid escaping issues in onclick
    overlay.innerHTML = `
        <div class="account-modal" role="dialog" aria-modal="true" aria-labelledby="revoke-key-modal-title"
             data-key-prefix="${accountEscapeHtml(keyPrefix)}">
            <div class="account-modal-header">
                <h2 class="account-modal-title" id="revoke-key-modal-title">Revoke API Key</h2>
                <button class="account-modal-close" onclick="closeAccountModal('revoke-key-modal-overlay')" aria-label="Close">&#215;</button>
            </div>
            <div class="account-modal-body">
                <p>Are you sure you want to revoke <strong>${accountEscapeHtml(keyName)}</strong>?</p>
                <p class="account-key-prefix-display">${accountEscapeHtml(keyPrefix)}...</p>
                <div class="account-revoke-warning">
                    This action cannot be undone. Any applications using this key will lose access immediately.
                </div>
                <div class="account-form-group" style="margin-top: 16px;">
                    <label class="account-form-label" for="revoke-reason-input">Reason (optional)</label>
                    <input type="text" id="revoke-reason-input" class="account-form-input"
                           placeholder="e.g. Security rotation" maxlength="200" />
                </div>
                <div id="revoke-key-error" class="account-form-error" style="display:none;"></div>
            </div>
            <div class="account-modal-footer">
                <button class="std-button secondary" onclick="closeAccountModal('revoke-key-modal-overlay')">
                    <span class="button-text">Cancel</span>
                </button>
                <button class="std-button danger" id="revoke-key-submit-btn" onclick="submitRevokeKey()">
                    <span class="button-text">Revoke Key</span>
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeAccountModal('revoke-key-modal-overlay');
    });
}

/**
 * Submit the revoke key request.
 * Reads key_prefix from the modal's data attribute.
 */
async function submitRevokeKey() {
    const overlay = document.getElementById('revoke-key-modal-overlay');
    const modal = overlay ? overlay.querySelector('.account-modal') : null;
    const keyPrefix = modal ? modal.dataset.keyPrefix : '';

    const reasonInput = document.getElementById('revoke-reason-input');
    const errorEl = document.getElementById('revoke-key-error');
    const submitBtn = document.getElementById('revoke-key-submit-btn');

    const reason = reasonInput ? reasonInput.value.trim() : '';

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.querySelector('.button-text').textContent = 'Revoking...';
    }
    if (errorEl) errorEl.style.display = 'none';

    try {
        const payload = {
            action: 'revokeApiKey',
            email: globalState.email,
            key_prefix: keyPrefix
        };
        if (reason) payload.reason = reason;

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!data.success) {
            const errMsg = data.error || 'Failed to revoke API key.';
            if (errorEl) { errorEl.textContent = errMsg; errorEl.style.display = 'block'; }
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.querySelector('.button-text').textContent = 'Revoke Key';
            }
            return;
        }

        closeAccountModal('revoke-key-modal-overlay');
        loadApiKeys();
    } catch (error) {
        console.error('[ACCOUNT] Error revoking key:', error);
        if (errorEl) { errorEl.textContent = 'Network error. Please try again.'; errorEl.style.display = 'block'; }
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.querySelector('.button-text').textContent = 'Revoke Key';
        }
    }
}

// ============================================================
// UTILITIES
// ============================================================

/**
 * Close an account modal overlay by element ID.
 */
function closeAccountModal(overlayId) {
    const overlay = document.getElementById(overlayId);
    if (overlay) overlay.remove();
}

/**
 * Format a UTC ISO timestamp as a human-readable relative time.
 */
function accountFormatRelativeTime(isoString) {
    try {
        const date = new Date(isoString);
        const diffMs = Date.now() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
        if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
        if (diffDays < 30) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
        return date.toLocaleDateString();
    } catch (_) {
        return isoString || 'Unknown';
    }
}

/**
 * Escape HTML special characters to prevent XSS.
 * Uses a dedicated name to avoid collision with any other escapeHtml in scope.
 */
function accountEscapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Expose functions needed by inline onclick handlers
window.initAccountPage = initAccountPage;
window.showCreateApiKeyModal = showCreateApiKeyModal;
window.submitCreateApiKey = submitCreateApiKey;
window.copyRawApiKey = copyRawApiKey;
window.showRevokeKeyModal = showRevokeKeyModal;
window.submitRevokeKey = submitRevokeKey;
window.closeAccountModal = closeAccountModal;
