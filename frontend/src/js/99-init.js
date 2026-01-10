/* ========================================
 * 99-init.js - Initialization & Startup
 *
 * Handles DOMContentLoaded event, state restoration,
 * navigation protection, and initial card creation.
 *
 * Dependencies: ALL other modules
 * ======================================== */

        // ============================================
        // INITIALIZATION
        // ============================================

        document.addEventListener('DOMContentLoaded', function() {
// Check for testing overrides before anything else
checkForTestingOverrides();

// MOBILE VERSION: Skip mobile detection to allow mobile usage
// if (isMobileDevice()) {
//     showMobileMessage();
//     return;
// }

// Fresh session - don't restore sessionId as backend will create new ones
// sessionId gets created when user uploads file or selects demo

// Restore email from localStorage if available
const storedEmail = localStorage.getItem('validatedEmail');
if (storedEmail && storedEmail.includes('@')) {
    globalState.email = storedEmail;
}

// Balance refresh system will be initialized when needed (when insufficient balance occurs)

// Prevent automatic scrolling during initial load
const originalScrollTo = window.scrollTo;
const originalScrollIntoView = Element.prototype.scrollIntoView;

// Temporarily disable scrolling
window.scrollTo = () => {};
Element.prototype.scrollIntoView = () => {};

// Check for saved state first
const hasHandledState = attemptStateRestore();

// Defer card creation to allow user to read content above first
setTimeout(() => {
    // Only create initial card if we're not restoring from saved state and haven't shown modal
    if (!window.isRestoringState && !hasHandledState) {
        createEmailCard();
    } else {
    }

    // Restore scrolling after card is created and settled
    setTimeout(() => {
        window.scrollTo = originalScrollTo;
        Element.prototype.scrollIntoView = originalScrollIntoView;
    }, 500);
}, 100);

// Test functions for animations
window.testErrorAnimation = (cardId = 'card-1') => {
    showThinkingInCard(cardId, 'Testing error animation...');
    setTimeout(() => {
        completeThinkingInCard(cardId, 'Generation failed');
    }, 2000);
};

window.testSuccessAnimation = (cardId = 'card-1') => {
    showThinkingInCard(cardId, 'Testing success animation...');
    setTimeout(() => {
        completeThinkingInCard(cardId, 'Generation complete!');
    }, 2000);
};

window.testProgressAnimation = (cardId = 'card-1') => {
    showThinkingInCard(cardId, 'Testing progress animation...', true);
    let progress = 0;
    const interval = setInterval(() => {
        progress += Math.random() * 15;
        if (progress >= 100) {
            progress = 100;
            clearInterval(interval);
            setTimeout(() => {
                completeThinkingInCard(cardId, 'Progress complete!');
            }, 500);
        }
        updateThinkingProgress(cardId, progress, `Processing... ${Math.round(progress)}%`);
    }, 200);
};

window.testProgressError = (cardId = 'card-1') => {
    showThinkingInCard(cardId, 'Testing progress error...', true);
    let progress = 0;
    const interval = setInterval(() => {
        progress += Math.random() * 10;
        if (progress >= 60) {
            clearInterval(interval);
            setTimeout(() => {
                completeThinkingInCard(cardId, 'Processing failed');
            }, 500);
            return;
        }
        updateThinkingProgress(cardId, progress, `Processing... ${Math.round(progress)}%`);
    }, 300);
};

        });

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
// Close all session WebSocket connections
sessionWebSockets.forEach((ws, sessionId) => {
    ws._intentionallyClosed = true;
    ws.close();
});
sessionWebSockets.clear();
cardHandlers.clear();
cardDummyProgress.clear();
cardCurrentProgress.clear();
registrationCounter = 0;
        });

        // Function to download preview results
        async function downloadPreviewResults(previewData) {
try {
    if (!globalState.sessionId) {
        throw new Error('No session ID available');
    }
    
    // Get version info
    const version = globalState.currentConfig?.config_version || 1;
    const originalFileName = globalState.excelFile?.name || 'preview_results';
    const fileNameBase = originalFileName.replace(/\.[^/.]+$/, ''); // Remove extension
    
    // Check if enhanced Excel download URL is available
    if (previewData.enhanced_download_url) {
        // Use the enhanced Excel download URL from backend
        const enhancedFileName = `${fileNameBase}_v${version}_preview_enhanced.xlsx`;
        
        const a = document.createElement('a');
        a.href = previewData.enhanced_download_url;
        a.download = enhancedFileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        return;
    }
    
    // Fallback to CSV if no enhanced Excel available
    let csvData = '';
    
    if (previewData.markdown_table) {
        // Parse the markdown table to extract data
        const lines = previewData.markdown_table.split('\n');
        let headers = [];
        let rows = [];
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line.startsWith('|') && line.endsWith('|')) {
                const cells = line.split('|').slice(1, -1).map(cell => cell.trim());
                if (i === 0 || (i === 1 && line.includes('---'))) {
                    if (i === 0) headers = cells;
                    // Skip separator line
                } else {
                    rows.push(cells);
                }
            }
        }
        
        // Convert to CSV
        if (headers.length > 0) {
            csvData = headers.join(',') + '\n';
            rows.forEach(row => {
                const escapedRow = row.map(cell => {
                    // Escape cells containing commas or quotes
                    if (cell.includes(',') || cell.includes('"') || cell.includes('\n')) {
                        return '"' + cell.replace(/"/g, '""') + '"';
                    }
                    return cell;
                });
                csvData += escapedRow.join(',') + '\n';
            });
        }
    } else {
        csvData = 'No preview data available\n';
    }
    
    // Create and download the file
    const blob = new Blob([csvData], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `${fileNameBase}_v${version}_preview.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
} catch (error) {
    console.error('Error downloading preview results:', error);
    alert(`Error downloading preview results: ${error.message}`);
}
        }

        // Function to download validation results
        window.downloadValidationResults = async function() {
try {
    if (!globalState.sessionId) {
        throw new Error('No session ID available');
    }
    
    let statusData;
    
    // First try to use completion data if available (should now include download URLs)
    if (globalState.completionData && (globalState.completionData.enhanced_download_url || globalState.completionData.download_url)) {
        statusData = globalState.completionData;
    } else {
        // Fallback: Check status API to get download URLs
        const response = await fetch(`${API_BASE}/status?session_id=${globalState.sessionId}`, {
            method: 'GET'
        });
        
        if (!response.ok) {
            throw new Error('Failed to get validation status');
        }
        
        statusData = await response.json();
    }
    
    // Get version from status data (more reliable than global state)
    const version = statusData.config_version || 
                   statusData.session_info?.config_version || 
                   globalState.currentConfig?.config_version || 1;
    
    const originalFileName = globalState.excelFile?.name || 'validation_results';
    const fileNameBase = originalFileName.replace(/\.[^/.]+$/, ''); // Remove extension
    
    // Prefer enhanced Excel download if available
    if (statusData.enhanced_download_url) {
        const enhancedFileName = `${fileNameBase}_v${version}_full_enhanced.xlsx`;
        
        const a = document.createElement('a');
        a.href = statusData.enhanced_download_url;
        a.download = enhancedFileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } else if (statusData.download_url) {
        // Fallback to ZIP download
        const zipFileName = `${fileNameBase}_v${version}_full_enhanced.zip`;
        
        const a = document.createElement('a');
        a.href = statusData.download_url;
        a.download = zipFileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } else {
        throw new Error('Results are not ready for download yet');
    }
} catch (error) {
    console.error('Error downloading results:', error);
    alert(`Error downloading results: ${error.message}`);
}
        }

        // Function to show confidence info modal
        function showConfidenceInfoModal() {
const modal = document.createElement('div');
modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
`;

const modalContent = document.createElement('div');
modalContent.style.cssText = `
    background: white;
    border-radius: 8px;
    padding: 20px;
    max-width: 600px;
    max-height: 80vh;
    overflow-y: auto;
    position: relative;
`;

modalContent.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h3 style="margin: 0; color: #333;">Results Structure & Confidence Levels</h3>
        <button onclick="this.closest('[style*=fixed]').remove()" style="background: none; border: none; font-size: 20px; cursor: pointer; color: #999;">×</button>
    </div>
    
    <div style="margin-bottom: 20px;">
        <h4 style="color: #007bff; margin-bottom: 10px;">📊 Excel File Structure</h4>
        <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
            <strong>Sheet 1: Updated Values</strong> - Your data with AI-enhanced and validated information<br>
            <strong>Sheet 2: Original Values</strong> - Your original data for reference<br>
            <strong>Sheet 3: Details</strong> - Detailed validation information, sources, and confidence scores
        </div>
    </div>
    
    <div style="margin-bottom: 20px;">
        <h4 style="color: #007bff; margin-bottom: 10px;">🎯 Confidence Levels</h4>
        <div style="display: grid; gap: 10px;">
            <div style="display: flex; align-items: center; padding: 8px; background: #d4edda; border-radius: 4px;">
                <span style="width: 20px; height: 20px; background: #28a745; border-radius: 3px; margin-right: 10px;"></span>
                <div>
                    <strong>HIGH (Green)</strong> - Verified information with reliable sources
                </div>
            </div>
            <div style="display: flex; align-items: center; padding: 8px; background: #fff3cd; border-radius: 4px;">
                <span style="width: 20px; height: 20px; background: #ffc107; border-radius: 3px; margin-right: 10px;"></span>
                <div>
                    <strong>MEDIUM (Yellow)</strong> - Reasonable information that may need verification
                </div>
            </div>
            <div style="display: flex; align-items: center; padding: 8px; background: #f8d7da; border-radius: 4px;">
                <span style="width: 20px; height: 20px; background: #dc3545; border-radius: 3px; margin-right: 10px;"></span>
                <div>
                    <strong>LOW (Red)</strong> - Information that requires manual verification
                </div>
            </div>
        </div>
    </div>
    
    <div style="background: #e7f3ff; padding: 15px; border-radius: 6px; border-left: 4px solid #007bff;">
        <strong>💡 Tip:</strong> The Enhanced Excel file includes cell comments with sources and detailed explanations. Hover over cells in Excel to see additional information.
    </div>
`;

modal.appendChild(modalContent);
document.body.appendChild(modal);

// Close on background click
modal.addEventListener('click', (e) => {
    if (e.target === modal) {
        modal.remove();
    }
});
        }

        // State Persistence Implementation
        function saveApplicationState() {
// Don't save if we're resetting or restoring
if (window.isResetting || window.isRestoringState) {
    return;
}

try {
    const state = {
        timestamp: Date.now(),
        pageType: detectPageType(), // Save current page type to prevent cross-page restoration
        scrollPosition: window.scrollY || 0,
        globalState: {
            ...globalState,
            // Don't save the debounceTimers Map as it can't be serialized
            debounceTimers: undefined
        },
        lastPreviewData: window.lastPreviewData || null,
        cards: []
    };

    // Save card states instead of innerHTML - but only main cards (not sub-elements)
    // Only select cards that match pattern card-X (where X is a number)
    const cards = document.querySelectorAll('[id^="card-"]');
    const mainCards = Array.from(cards).filter(card => /^card-\d+$/.test(card.id));
    mainCards.forEach(card => {
        const title = card.querySelector('.card-title')?.textContent || '';
        const content = card.querySelector('.card-content')?.innerHTML || '';

        // Strip HTML and check for meaningful content
        const cleanTitle = title.replace(/<[^>]*>/g, '').trim();
        const cleanContent = content.replace(/<[^>]*>/g, '').trim();

        // Skip blank or nearly empty cards (must have at least 5 meaningful characters)
        if (cleanTitle.length < 2 && cleanContent.length < 5) {
            return;
        }

        const cardData = {
            id: card.id,
            type: card.dataset.cardType || 'unknown',
            title: title,
            content: content,
            isCompleted: card.classList.contains('completed'),
            isProcessing: card.querySelector('.thinking-indicator') !== null
        };

        // Debug logging for preview cards
        if (card.id === 'card-4' || title.includes('Preview')) {
        }

        // Save form data within this card
        const cardInputs = card.querySelectorAll('input, textarea, select');
        const cardFormData = {};
        cardInputs.forEach(input => {
            if (input.id || input.name) {
                const key = input.id || input.name;
                if (input.type === 'checkbox' || input.type === 'radio') {
                    cardFormData[key] = input.checked;
                } else if (input.type !== 'file') {
                    cardFormData[key] = input.value;
                }
            }
        });
        cardData.formData = cardFormData;

        state.cards.push(cardData);
    });

    // Save global form inputs
    const globalInputs = document.querySelectorAll('body > input, body > textarea, body > select');
    const globalFormData = {};
    globalInputs.forEach(input => {
        if (input.id || input.name) {
            const key = input.id || input.name;
            if (input.type === 'checkbox' || input.type === 'radio') {
                globalFormData[key] = input.checked;
            } else if (input.type !== 'file') {
                globalFormData[key] = input.value;
            }
        }
    });
    state.globalFormData = globalFormData;

    sessionStorage.setItem('hyperplexity_app_state', JSON.stringify(state));
} catch (error) {
    console.warn('[WARN] Could not save application state:', error);
}
        }

        function restoreApplicationState() {
try {
    const savedState = sessionStorage.getItem('hyperplexity_app_state');
    if (!savedState) return false;

    const state = JSON.parse(savedState);

    // Check if state is recent (within 1 hour)
    const oneHour = 60 * 60 * 1000;
    if (Date.now() - state.timestamp > oneHour) {
        sessionStorage.removeItem('hyperplexity_app_state');
        return false;
    }

    // Restore cards using the createCard function (if available)
    const cardContainer = document.getElementById('cardContainer');
    if (cardContainer && state.cards && state.cards.length > 0) {
        // Clear existing cards first
        clearExistingCards();

        // Recreate each saved card - but only if it has valid content
        let validCardsRestored = 0;
        state.cards.forEach(cardData => {
            try {
                // Validate card data before restoring - be very strict
                const hasValidId = cardData.id && cardData.id.trim() !== '';
                const cleanTitle = (cardData.title || '').replace(/<[^>]*>/g, '').trim();
                const cleanContent = (cardData.content || '').replace(/<[^>]*>/g, '').trim();

                // Skip blank or invalid cards - require meaningful content
                if (!hasValidId || (cleanTitle.length < 2 && cleanContent.length < 5)) {
                    return;
                }

                // Create a basic card structure
                const cardElement = document.createElement('div');
                cardElement.id = cardData.id;
                cardElement.className = 'card';
                if (cardData.type) {
                    cardElement.dataset.cardType = cardData.type;
                }
                if (cardData.isCompleted) {
                    cardElement.classList.add('completed');
                }

                // Set card content
                cardElement.innerHTML = `
                    <div class="card-header">
                        <h3 class="card-title">${cardData.title || 'Untitled'}</h3>
                    </div>
                    <div class="card-content">${cardData.content || ''}</div>
                `;

                cardContainer.appendChild(cardElement);
                validCardsRestored++;

                // Re-initialize button functionality for this card
                reinitializeCardButtons(cardElement, cardData);

                // Restore form data for this card
                if (cardData.formData) {
                    Object.entries(cardData.formData).forEach(([key, value]) => {
                        const element = cardElement.querySelector(`#${key}, [name="${key}"]`);
                        if (element) {
                            if (element.type === 'checkbox' || element.type === 'radio') {
                                element.checked = value;
                            } else if (element.type !== 'file') {
                                element.value = value;
                            }
                        }
                    });
                }
            } catch (cardError) {
                console.warn('[WARN] Could not restore card:', cardData.id, cardError);
            }
        });

        // Log restoration results

        // If no valid cards were restored, fall back to normal initialization
        if (validCardsRestored === 0) {
            window.isRestoringState = false;
            return false;
        }
    }

    // Restore global form inputs
    if (state.globalFormData) {
        Object.entries(state.globalFormData).forEach(([key, value]) => {
            const element = document.getElementById(key) || document.querySelector(`[name="${key}"]`);
            if (element && !element.closest('[id^="card-"]')) { // Only global inputs
                if (element.type === 'checkbox' || element.type === 'radio') {
                    element.checked = value;
                } else if (element.type !== 'file') {
                    element.value = value;
                }
            }
        });
    }

    // Restore scroll position
    if (state.scrollPosition) {
        setTimeout(() => {
            window.scrollTo(0, state.scrollPosition);
        }, 200);
    }

    // Restore global state with proper initialization
    if (state.globalState) {
        Object.assign(globalState, state.globalState);

        // Ensure debounceTimers is properly initialized as a Map
        if (!globalState.debounceTimers || !(globalState.debounceTimers instanceof Map)) {
            globalState.debounceTimers = new Map();
        }

        // Ensure processingState is properly initialized
        if (!globalState.processingState || typeof globalState.processingState !== 'object') {
            globalState.processingState = {
                previewCompleted: false,
                validationCompleted: false,
                validationStartTime: null,
                previewStartTime: null,
                lastEstimatedCost: null,
                lastBalanceCheck: null
            };
        }

    }

    // Restore preview data
    if (state.lastPreviewData) {
        window.lastPreviewData = state.lastPreviewData;
    }

    // Show a brief notification that state was restored

    // Clear the restoration flag after a delay to allow normal card creation
    setTimeout(() => {
        window.isRestoringState = false;
    }, 1000);

    return true;
} catch (error) {
    console.warn('[WARN] Could not restore application state:', error);
    sessionStorage.removeItem('hyperplexity_app_state');
    return false;
}
        }

        // Save state before page unload
        window.addEventListener('beforeunload', saveApplicationState);

        // Save state periodically during user interaction
        let stateChangeTimeout;
        function scheduleStateSave() {
// Don't schedule saves if we're resetting
if (window.isResetting || window.isRestoringState) {
    return;
}
clearTimeout(stateChangeTimeout);
stateChangeTimeout = setTimeout(saveApplicationState, 1000);
        }

        // Monitor form changes and user interactions
        document.addEventListener('input', scheduleStateSave);
        document.addEventListener('change', scheduleStateSave);

        // Update reset button appearance based on state
        function updateResetButtonAppearance() {
const resetButton = document.querySelector('.reset-button');
const hasState = sessionStorage.getItem('hyperplexity_app_state') !== null;
const cardCount = document.querySelectorAll('[id^="card-"]').length;

if (resetButton) {
    if (hasState && cardCount > 1) {
        resetButton.classList.add('has-state');
        resetButton.title = 'Reset page and clear saved progress - You have saved state (Ctrl+Shift+R)';
    } else {
        resetButton.classList.remove('has-state');
        resetButton.title = 'Reset page and clear saved progress (Ctrl+Shift+R)';
    }
}
        }

        // Update button appearance periodically
        setInterval(updateResetButtonAppearance, 2000);

        // Handle page show event (when returning from back/forward navigation)
        window.addEventListener('pageshow', function(event) {
if (event.persisted) {
    // Page was restored from browser cache
    restoreApplicationState();
}
        });

        // Global flag to track if we're restoring state
        window.isRestoringState = false;


        // Try to restore state when DOM is loaded - BEFORE other initialization
        function attemptStateRestore() {
const hasState = sessionStorage.getItem('hyperplexity_app_state');
if (hasState) {
    try {
        const state = JSON.parse(hasState);
        const cardCount = (state.cards || []).length;
        const oneHour = 60 * 60 * 1000;

        // Check if state is recent (within 1 hour)
        if (Date.now() - state.timestamp > oneHour) {
            sessionStorage.removeItem('hyperplexity_app_state');
            return false;
        }

        // Check if page type has changed (don't restore state from different page types)
        const currentPageType = detectPageType();
        const savedPageType = state.pageType || 'default';
        if (currentPageType !== savedPageType) {
            console.log(`[STATE] Page type changed from ${savedPageType} to ${currentPageType}, clearing saved state`);
            sessionStorage.removeItem('hyperplexity_app_state');
            return false;
        }

        if (cardCount >= 2) {
            // Check if this was a page refresh (performance navigation timing)
            if (performance && performance.getEntriesByType) {
                const navEntries = performance.getEntriesByType('navigation');
                if (navEntries.length > 0 && navEntries[0].type === 'reload') {
                    return false;
                }
            }

            // Auto-restore for navigation back/forward
            return restoreApplicationState();
        } else {
            sessionStorage.removeItem('hyperplexity_app_state');
            return false;
        }
    } catch (error) {
        console.warn('[AUTO] Invalid saved state, clearing:', error);
        sessionStorage.removeItem('hyperplexity_app_state');
        return false;
    }
}
return false;
        }

        // Helper function to clear any existing cards before restoration
        function clearExistingCards() {
const cardContainer = document.getElementById('cardContainer');
if (cardContainer) {
    cardContainer.innerHTML = '';
}
        }

        // Function to re-initialize all functionality after card restoration
        function reinitializeCardButtons(cardElement, cardData) {
const cardId = cardData.id;

try {
    // Re-attach event handlers based on card type and content
    const buttons = cardElement.querySelectorAll('button');

    buttons.forEach(button => {
        const buttonText = button.textContent.trim();
        const buttonClass = button.className;
        const dataAction = button.getAttribute('data-action');

        // Debug logging for Process Table button detection
        if (cardId === 'card-4' || buttonText.toLowerCase().includes('process')) {
        }

        // Email validation buttons
        if (buttonText.includes('Send Code') || buttonText.includes('Validate Email') || button.id.includes('send-code')) {
            button.onclick = () => sendValidationCode(cardId, button);

        } else if (buttonText.includes('Verify') || buttonText.includes('Submit Code') || button.id.includes('verify-code')) {
            button.onclick = () => verifyCode(cardId, button);

        // File upload and configuration buttons
        } else if (buttonText.includes('Browse Files') || buttonClass.includes('browse-button')) {
            const fileInput = cardElement.querySelector('input[type="file"]');
            if (fileInput) {
                button.onclick = () => fileInput.click();
            }

        } else if (buttonText.includes('Recent Config') || buttonClass.includes('recent-config')) {
            button.onclick = () => selectRecentConfig(cardId, button);

        } else if (buttonText.includes('Use Match') || buttonClass.includes('use-match')) {
            const configKey = button.dataset.configKey;
            const sourceSession = button.dataset.sourceSession;
            if (configKey) {
                button.onclick = () => window.useMatchingConfig(configKey, sourceSession);
            }

        } else if (buttonText.includes('Generate with AI') || buttonClass.includes('ai-generate')) {
            button.onclick = () => generateWithAI(cardId);

        // Process and download buttons
        } else if (buttonText.includes('Process Table') || buttonText.includes('Start Processing') || buttonClass.includes('process-button') || button.id.includes('process')) {
            button.onclick = () => startFullProcessing(cardId);

        } else if (dataAction === 'download-preview' || buttonText.includes('Download Rich Preview')) {
            button.onclick = async () => {
                try {
                    markDownloadStart();
                    if (window.lastPreviewData) {
                        await downloadPreviewResults(window.lastPreviewData);
                    } else {
                        await downloadPreviewResults();
                    }
                } catch (error) {
                    console.error('Preview download error:', error);
                    alert('Download failed: ' + error.message);
                }
            };

        } else if (dataAction === 'refine-config' || buttonText.includes('Refine Configuration')) {
            // Check if debounceConfigAction is available
            if (typeof debounceConfigAction === 'function') {
                button.onclick = debounceConfigAction('refine-config', async () => {
                    try {
                        await window.createRefinementCard();
                    } catch (error) {
                        console.error('Refine error:', error);
                        alert('Refine failed: ' + error.message);
                    }
                });
            } else {
                // Fallback without debouncing
                button.onclick = async () => {
                    try {
                        await window.createRefinementCard();
                    } catch (error) {
                        console.error('Refine error:', error);
                        alert('Refine failed: ' + error.message);
                    }
                };
            }

        } else if (dataAction === 'revert-config' || buttonText.includes('Revert to Previous')) {
            // Check if debounceConfigAction is available
            if (typeof debounceConfigAction === 'function') {
                button.onclick = debounceConfigAction('revert-config-generic', async () => {
                    try {
                        button.disabled = true;
                        button.textContent = '↩️ Reverting...';
                        await createConfigCardWithId('last');
                    } catch (error) {
                        console.error('Revert error:', error);
                        alert('Revert failed: ' + error.message);
                        button.disabled = false;
                        button.textContent = '↩️ Revert to Previous';
                    }
                });
            } else {
                // Fallback without debouncing
                button.onclick = async () => {
                    try {
                        button.disabled = true;
                        button.textContent = '↩️ Reverting...';
                        await createConfigCardWithId('last');
                    } catch (error) {
                        console.error('Revert error:', error);
                        alert('Revert failed: ' + error.message);
                        button.disabled = false;
                        button.textContent = '↩️ Revert to Previous';
                    }
                };
            }

        } else if (buttonText.includes('Preparing Download') || (buttonText.includes('Download') && button.disabled)) {
            // Enable the download button and set proper handler
            button.disabled = false;
            const buttonTextElement = button.querySelector('.button-text');
            if (buttonTextElement) {
                buttonTextElement.textContent = '📥 Download Results';
            }
            button.onclick = async () => {
                try {
                    markDownloadStart();
                    await window.downloadValidationResults();
                } catch (error) {
                    console.error('Download error:', error);
                    alert('Download failed: ' + error.message);
                }
            };

        } else if (buttonText.includes('Download Results') || buttonClass.includes('download-button')) {
            button.onclick = async () => {
                try {
                    markDownloadStart();
                    await window.downloadValidationResults();
                } catch (error) {
                    console.error('Download error:', error);
                    alert('Download failed: ' + error.message);
                }
            };
        }
    });

    // Re-initialize file inputs with proper drag & drop
    const fileInputs = cardElement.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        const inputId = input.id || input.name || '';

        if (inputId.includes('file')) {
            // Excel file upload
            input.onchange = (e) => handleFileSelect(e, cardId);
        } else if (inputId.includes('config')) {
            // Config file upload
            input.onchange = (e) => handleConfigUpload(e, cardId);
        }
    });

    // Re-initialize drop zones
    const dropZones = cardElement.querySelectorAll('.drop-zone');
    dropZones.forEach(dropZone => {
        setupFileUpload(cardId);
    });

    // Try to fix buttons on all cards - let the function decide what to do
    recreateProcessTableButton(cardElement, cardId);

} catch (error) {
    console.warn(`[WARN] Could not reinitialize card functionality ${cardId}:`, error);
}
        }

        // Removed createCompletedButton - was causing duplicate download buttons

        // Special function to recreate Process Table button for preview cards
        function recreateProcessTableButton(cardElement, cardId) {
try {

    // SIMPLE APPROACH: If the card already has working buttons, don't touch them
    const existingButtons = cardElement.querySelectorAll('button');
    const hasWorkingDownload = Array.from(existingButtons).some(btn =>
        btn.textContent.includes('Download Results') && !btn.disabled && btn.onclick
    );

    if (hasWorkingDownload) {
        return;
    }

    // Check if this is a preview card with cost estimates
    const cardContent = cardElement.innerHTML || '';
    const hasCostEstimate = cardContent.includes('Cost') && cardContent.includes('Credits Needed');

    if (hasCostEstimate) {
        // This is a preview card - create process/credits button with balance checking
        createProcessTableButtonWithBalance(cardElement, cardId);
    } else {
        // Not a preview card - leave it alone unless it's clearly broken
    }

} catch (error) {
    console.warn(`[WARN] Could not recreate button for ${cardId}:`, error);
}
        }

        // Helper function to create Process Table button with balance checking
        function createProcessTableButtonWithBalance(cardElement, cardId) {
try {
    // Extract cost and balance from card content if available
    const cardContent = cardElement.innerHTML || '';
    let extractedCost = 0;
    let extractedBalance = 0;

    // Look for cost in the card content (e.g., "Cost\n$2.00")
    const costMatch = cardContent.match(/Cost[^$]*\$(\d+\.?\d*)/);
    if (costMatch) {
        extractedCost = parseFloat(costMatch[1]);
    }

    // Look for balance in the card content (e.g., "Your Balance\n$0.00")
    const balanceMatch = cardContent.match(/Your Balance[^$]*\$(\d+\.?\d*)/);
    if (balanceMatch) {
        extractedBalance = parseFloat(balanceMatch[1]);
    }

    // Use extracted values or fall back to global state
    const currentBalance = extractedBalance || globalState.accountBalance || 0;
    const estimatedCost = extractedCost || globalState.estimatedCost || 0;
    const effectiveCost = globalState.effectiveCost ?? estimatedCost; // Use ?? not || so 0 doesn't fall back
    const sufficientBalance = currentBalance >= effectiveCost;

    // Update global state with extracted values
    if (extractedCost > 0) globalState.estimatedCost = extractedCost;
    if (extractedBalance >= 0) globalState.accountBalance = extractedBalance;


    // Check for updated balance and pending orders during restore
    setTimeout(async () => {
        try {
            // Skip if no email available
            if (!globalState.email) {
                return;
            }


            // Check for balance update - but only call if we have necessary data
            if (globalState.sessionId && globalState.email) {
                try {
                    const balanceResponse = await fetch(`${API_BASE}/validate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            email: globalState.email,
                            action: 'getAccountBalance'
                        })
                    });

                    if (balanceResponse.ok) {
                        const balanceData = await balanceResponse.json();
                        if (balanceData.success) {
                            // Handle different response formats (same as existing balance code)
                            let newBalance = balanceData.balance;
                            if (newBalance === undefined && balanceData.account_info) {
                                newBalance = balanceData.account_info.balance || balanceData.account_info.current_balance;
                            }

                            if (typeof newBalance === 'number') {
                                const oldBalance = globalState.accountBalance || 0;

                                if (Math.abs(newBalance - oldBalance) > 0.001) {
                                    globalState.accountBalance = newBalance;

                                    // Check if balance became sufficient and user previously attempted processing
                                    const newSufficientBalance = newBalance >= effectiveCost;


                                    if (newSufficientBalance && !sufficientBalance && globalState.userAttemptedProcessing && globalState.pendingProcessingTrigger) {

                                        // Clear blue message and show green success message (same as tab focus)
                                        const messageContainers = document.querySelectorAll('[id$="-messages"]');

                                        if (messageContainers.length > 0) {
                                            const lastContainer = messageContainers[messageContainers.length - 1];
                                            const containerId = lastContainer.id;

                                            // Clear existing messages
                                            const container = document.getElementById(containerId);
                                            if (container) {
                                                container.innerHTML = '';
                                            }

                                            showMessage(containerId, `🎉 Balance updated! Auto-starting validation...`, 'success', false, 'auto-process');
                                        }

                                        // Trigger auto-processing (same as tab focus)
                                        setTimeout(() => {
                                            try {
                                                globalState.pendingProcessingTrigger();
                                            } catch (error) {
                                                console.error(`[ERROR] Auto-processing trigger failed:`, error);
                                            }
                                            globalState.userAttemptedProcessing = false;
                                            globalState.pendingProcessingTrigger = null;
                                        }, 1000);

                                        return; // Exit early, processing will start automatically
                                    } else if (newSufficientBalance !== sufficientBalance) {
                                        // Balance status changed but no auto-processing - just recreate button
                                        recreateProcessTableButton(cardElement, cardId);
                                        return;
                                    }
                                }
                            }
                        }
                    } else {
                        const errorText = await balanceResponse.text();
                        console.warn(`[RESTORE] Balance check failed (${balanceResponse.status}):`, errorText);
                    }
                } catch (balanceError) {
                    console.warn(`[RESTORE] Balance check error:`, balanceError);
                }
            }

            // Check for pending Squarespace orders - separate try/catch
            try {
                const orderResponse = await fetch(`${API_BASE}/validate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: globalState.email,
                        action: 'checkSquarespaceOrders'
                    })
                });

                if (orderResponse.ok) {
                    const orderData = await orderResponse.json();
                    if (orderData.success && orderData.new_orders_found) {

                        // Update balance if provided in the response
                        if (typeof orderData.new_balance === 'number') {
                            const oldBalance = globalState.accountBalance || 0;
                            globalState.accountBalance = orderData.new_balance;

                            // Check for auto-processing trigger (same logic as balance check)
                            const orderSufficientBalance = orderData.new_balance >= effectiveCost;
                            if (orderSufficientBalance && !sufficientBalance && globalState.userAttemptedProcessing && globalState.pendingProcessingTrigger) {
                                // Show success message and trigger auto-processing
                                const messageContainers = document.querySelectorAll('[id$="-messages"]');
                                if (messageContainers.length > 0) {
                                    const lastContainer = messageContainers[messageContainers.length - 1];
                                    const containerId = lastContainer.id;
                                    const container = document.getElementById(containerId);
                                    if (container) {
                                        container.innerHTML = '';
                                    }
                                    showMessage(containerId, `🎉 Order processed! Auto-starting validation...`, 'success', false, 'auto-process');
                                }

                                setTimeout(() => {
                                    globalState.pendingProcessingTrigger();
                                    globalState.userAttemptedProcessing = false;
                                    globalState.pendingProcessingTrigger = null;
                                }, 1000);

                                return;
                            }
                        }

                        // Fallback: trigger another balance check after order processing if no balance provided
                        setTimeout(() => {
                            recreateProcessTableButton(cardElement, cardId);
                        }, 2000);
                        return; // Exit early, button will be recreated
                    }
                } else {
                    const errorText = await orderResponse.text();
                    console.warn(`[RESTORE] Order polling failed (${orderResponse.status}):`, errorText);
                }
            } catch (orderError) {
                console.warn(`[RESTORE] Order polling error:`, orderError);
            }
        } catch (error) {
            console.warn(`[RESTORE] Failed to check balance/orders for ${cardId}:`, error);
        }
    }, 500); // Small delay to not interfere with initial button creation

    // Ensure button container exists
    let buttonContainer = cardElement.querySelector(`#${cardId}-buttons`);
    if (!buttonContainer) {
        const cardContent = cardElement.querySelector('.card-content');
        if (cardContent) {
            buttonContainer = document.createElement('div');
            buttonContainer.id = `${cardId}-buttons`;
            buttonContainer.style.cssText = 'margin-top: 20px; text-align: center;';
            cardContent.appendChild(buttonContainer);
        } else {
            return;
        }
    }

    // Reuse existing button creation logic (same as in preview cards)
    const creditsNeeded = Math.max(0, effectiveCost - currentBalance);

    // Use effectiveCost already declared at line 9726
    const discount = globalState.discount || 0;

    let buttonCostText = '';
    if (estimatedCost) {
        if (discount > 0) {
            // Show strikethrough original cost → discounted price (same format as cost display)
            buttonCostText = ` (<span style="text-decoration: line-through;">$${estimatedCost.toFixed(2)}</span> → $${effectiveCost.toFixed(2)})`;
        } else {
            buttonCostText = ` ($${estimatedCost.toFixed(2)})`;
        }
    }

    createButtonRow(`${cardId}-buttons`, [
        {
            text: sufficientBalance
                ? `Process Table${buttonCostText}`
                : `Add Credits ($${Math.ceil(creditsNeeded).toFixed(2)})`,
            icon: sufficientBalance ? '✨' : '💳',
            variant: sufficientBalance ? 'primary' : 'secondary',
            width: 'full',
            callback: async (e) => {
                const button = e.target.closest('button');

                if (sufficientBalance) {
                    markButtonSelected(button, '✨ Processing...');
                    globalState.activePreviewCard = null;
                    createProcessingCard();
                } else {
                    markButtonSelected(button, '💳 Opening store...');
                    const recommendedAmount = Math.ceil(creditsNeeded);
                    openAddCreditsPage(recommendedAmount, `${cardId}-messages`);

                    setTimeout(() => {
                        markButtonUnselected(button);
                    }, 2000);
                }
            }
        }
    ]);

    // Show instruction message for Add Credits button
    if (!sufficientBalance) {
        showMessage(`${cardId}-messages`, `💳 Click button to add credits. After purchase, return to this tab for auto-processing.`, 'info', false, 'add-credits-instruction');
    }

} catch (error) {
    console.warn(`[WARN] Could not recreate button for ${cardId}:`, error);
}
        }

        // Flag to prevent auto-save during reset
        window.isResetting = false;

        // Reset page functionality - clears saved state and reloads
        window.resetPage = function() {
try {
    // Set reset flag to prevent auto-save
    window.isResetting = true;
    window.isRestoringState = false;

    // Clear saved state multiple times to ensure it's gone
    sessionStorage.removeItem('hyperplexity_app_state');
    sessionStorage.clear(); // Clear all session storage just to be sure

    // Force reload with cache bypass
    window.location.reload(true);
} catch (error) {
    console.warn('[WARN] Could not reset page:', error);
    // Fallback: force reload with cache bypass
    window.location.href = window.location.href + '?reset=' + Date.now();
}
        }

        // Emergency reset function that's more aggressive
        window.hardReset = function() {
window.isResetting = true;
window.isRestoringState = false;

// Clear all storage
try {
    sessionStorage.clear();
    localStorage.clear();
} catch (e) {}

// Clear the card container immediately
const cardContainer = document.getElementById('cardContainer');
if (cardContainer) {
    cardContainer.innerHTML = '';
}

// Force navigation to current page with timestamp to bypass cache
window.location.href = window.location.pathname + '?reset=' + Date.now();
        }

        // Add keyboard shortcut for reset (Ctrl+Shift+R or Cmd+Shift+R)
        document.addEventListener('keydown', function(event) {
if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'R') {
    event.preventDefault();
    if (confirm('Reset page and clear all saved progress?')) {
        resetPage();
    }
}
        });

        // Console helper function
        window.clearState = function() {
sessionStorage.removeItem('hyperplexity_app_state');
        };

        // Debug function to inspect saved state
        window.inspectState = function() {
const saved = sessionStorage.getItem('hyperplexity_app_state');
if (saved) {
    const state = JSON.parse(saved);
    if (state.cards) {
        state.cards.forEach((card, i) => {
            const cleanTitle = (card.title || '').replace(/<[^>]*>/g, '').trim();
            const cleanContent = (card.content || '').replace(/<[^>]*>/g, '').trim();
        });
    }
} else {
}
        };

        // Show available reset methods in console

        // ============================================
        // NAVIGATION PROTECTION & RESTORE SYSTEM
        // ============================================

        // Track if we have valuable data that shouldn't be lost
        function hasValuableData() {
return globalState.excelFileUploaded ||
       globalState.currentConfig ||
       document.querySelectorAll('[id^="card-"]').length > 1;
        }

        // Track download operations to avoid triggering warnings
        let isDownloading = false;

        // Helper function to mark download start
        window.markDownloadStart = function() {
isDownloading = true;
// Reset flag after a short delay in case download doesn't trigger beforeunload
setTimeout(() => {
    isDownloading = false;
}, 3000);
        };

        // Simple beforeunload warning - no custom modals
        window.addEventListener('beforeunload', (e) => {
// Don't warn if user explicitly clicked "New Validation" or is downloading
if (hasValuableData() && !isDownloading && !window.isResetting) {
    // Save state for navigation (not refresh)
    if (typeof saveApplicationState === 'function') {
        saveApplicationState();
    }

    // Show browser's native warning
    const message = 'You have uploaded data and made progress. Are you sure you want to leave?';
    e.returnValue = message;
    return message;
}

// Reset download flag regardless
if (isDownloading) {
    isDownloading = false;
}

// Log if resetting
if (window.isResetting) {
}
        });

        // Handle page visibility changes (back/forward navigation)
        document.addEventListener('visibilitychange', () => {
if (!document.hidden) {
    // Tab became visible, checking connections

    // Reconnect any disconnected WebSockets
    sessionWebSockets.forEach((ws, sessionId) => {
        if (ws.readyState !== WebSocket.OPEN && ws.readyState !== WebSocket.CONNECTING) {
            // Reconnecting WebSocket
            sessionWebSockets.delete(sessionId);
            connectToSession(sessionId, 0); // Reset reconnect attempts
        }
    });

    // Small delay to ensure state is ready
    setTimeout(() => {
        if (hasValuableData()) {
            return;
        }

        // Check if we have saved state
        const savedState = sessionStorage.getItem('hyperplexity_app_state');
        if (savedState) {
            try {
                const state = JSON.parse(savedState);
                const oneHour = 60 * 60 * 1000;

                if (Date.now() - state.timestamp <= oneHour && state.cards && state.cards.length > 1) {
                    // Auto-restore without modal
                    if (typeof restoreApplicationState === 'function') {
                        restoreApplicationState();
                    }
                } else if (Date.now() - state.timestamp > oneHour) {
                    sessionStorage.removeItem('hyperplexity_app_state');
                }
            } catch (error) {
                console.warn('[NAV] Error checking saved state:', error);
            }
        }
    }, 100);
}
        });




        // Note: State restoration is now handled in the main DOMContentLoaded event
        // to avoid conflicts with card initialization

        // Validator timeout warning functions
        function showValidatorDeathWarning(cardId, sessionId) {

// Update progress text to show warning (less dramatic, recoverable)
const progressText = document.querySelector(`#${cardId} .progress-text`);
if (progressText) {
    progressText.textContent = 'No updates for 3 minutes - validator may be stalled. Waiting for recovery...';
    progressText.style.color = '#ff9800'; // Orange warning color
}

// Mark as having shown warning for recovery
const timeoutInfo = window.asyncTimeouts && window.asyncTimeouts.get(sessionId);
if (timeoutInfo) {
    timeoutInfo.warningShown = true;
}

// Make the progress square pulse faster to indicate issue
const progressSquare = document.querySelector(`#${cardId} .progress-square, #${cardId} .thinking-square`);
if (progressSquare) {
    progressSquare.classList.add('fast-heartbeat');
}
        }

        function showTimeoutWarning(cardId, sessionId, timeoutMinutes) {

// Complete thinking animation with warning
completeThinkingInCard(cardId, 'Validation taking longer than expected');

// Show warning message
const warningHtml = `
    <div style="background: #fff3e0; border: 1px solid #ff9800; border-radius: 8px; padding: 16px; margin: 16px 0;">
        <h4 style="color: #ef6c00; margin: 0 0 8px 0;">⏰ Validation Timeout</h4>
        <p style="margin: 0 0 8px 0; color: #424242;">
            The validation process has exceeded the expected runtime of ${timeoutMinutes} minutes.
        </p>
        <p style="margin: 0 0 12px 0; color: #424242;">
            The validator may have failed or be processing a larger dataset than estimated.
        </p>
        <div style="margin-top: 12px;">
            <button onclick="location.reload()" style="background: #ff9800; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 8px;">
                Check Status
            </button>
            <button onclick="window.open('mailto:support@eliyahu.ai?subject=Validation Timeout&body=Session ID: ${sessionId}', '_blank')"
                    style="background: #666; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                Contact Support
            </button>
        </div>
    </div>
`;

showMessage(`${cardId}-messages`, warningHtml, 'warning');
        }

        // ============================================
