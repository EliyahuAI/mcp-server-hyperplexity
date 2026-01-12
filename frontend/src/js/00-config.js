/* ========================================
 * Configuration Module
 * Environment detection, API configuration, and global state management
 *
 * Dependencies: None (loaded first)
 * ======================================== */

// ============================================
// ENVIRONMENT CONFIGURATION
// ============================================

// Environment configurations for different deployment targets
const ENV_CONFIGS = {
    dev: {
        apiBase: 'https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev',
        websocketUrl: 'wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',
        storeUrl: 'https://eliyahu.ai/store/p/10-hyperplexity-credits',
        termsUrl: 'https://eliyahu.ai/terms',
        privacyUrl: 'https://eliyahu.ai/privacy-notice'
    },
    test: {
        apiBase: 'https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod',
        websocketUrl: 'wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',
        storeUrl: 'https://eliyahu.ai/store/p/10-hyperplexity-credits',
        termsUrl: 'https://eliyahu.ai/terms',
        privacyUrl: 'https://eliyahu.ai/privacy-notice'
    },
    staging: {
        apiBase: 'https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod',
        websocketUrl: 'wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',
        storeUrl: 'https://eliyahu.ai/store/p/10-hyperplexity-credits',
        termsUrl: 'https://eliyahu.ai/terms',
        privacyUrl: 'https://eliyahu.ai/privacy-notice'
    },
    prod: {
        apiBase: 'https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod',
        websocketUrl: 'wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',
        storeUrl: 'https://eliyahu.ai/store/p/10-hyperplexity-credits',
        termsUrl: 'https://eliyahu.ai/terms',
        privacyUrl: 'https://eliyahu.ai/privacy-notice'
    }
};

// ============================================
// FLEXIBLE ENVIRONMENT DETECTION
// ============================================

// Method 1: Check localStorage for saved environment preference
function getStoredEnvironment() {
    try {
        return localStorage.getItem('hyperplexity_environment');
    } catch (e) {
        return null;
    }
}

// Method 2: Page name detection (for Squarespace)
function detectEnvironmentFromPageName() {
    const pathname = window.location.pathname;
    const pageName = pathname.split('/').pop() || pathname;

    // Strip file extension to check the base name
    const baseNameWithoutExt = pageName.replace(/\.[^/.]+$/, '');

    if (baseNameWithoutExt.endsWith('-dev')) {
        return 'dev';
    } else if (baseNameWithoutExt.endsWith('-test')) {
        return 'test';
    } else if (baseNameWithoutExt.endsWith('-staging')) {
        return 'staging';
    }
    return null;
}

// Method 3: Check URL parameters
function getEnvironmentFromURL() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('env') || urlParams.get('environment');
}

// Main environment detection with multiple fallbacks
function detectEnvironment() {
    let environment = null;
    let detectionMethod = 'default';

    // Priority 1: URL parameter (highest priority - for testing/overrides)
    environment = getEnvironmentFromURL();
    if (environment && ENV_CONFIGS[environment]) {
        detectionMethod = 'URL parameter';

        // Save to localStorage for future visits
        try {
            localStorage.setItem('hyperplexity_environment', environment);
        } catch (e) {
            console.warn('[WARN] Could not save environment preference to localStorage');
        }

        return environment;
    }

    // Priority 2: Page name detection (for Squarespace)
    environment = detectEnvironmentFromPageName();
    if (environment && ENV_CONFIGS[environment]) {
        detectionMethod = 'page name';
        return environment;
    }

    // Priority 3: Stored environment preference
    environment = getStoredEnvironment();
    if (environment && ENV_CONFIGS[environment]) {
        detectionMethod = 'stored preference';
        return environment;
    }

    // Default: Production
    return 'prod';
}

// Function to manually set environment (for programmatic use)
function setEnvironment(env) {
    if (!ENV_CONFIGS[env]) {
        console.error(`[ERROR] Invalid environment: ${env}. Valid options:`, Object.keys(ENV_CONFIGS));
        return false;
    }

    try {
        localStorage.setItem('hyperplexity_environment', env);
        return true;
    } catch (e) {
        console.error('[ERROR] Could not save environment preference:', e);
        return false;
    }
}

// Function to clear environment preference
function clearEnvironmentPreference() {
    try {
        localStorage.removeItem('hyperplexity_environment');
    } catch (e) {
        console.error('[ERROR] Could not clear environment preference:', e);
    }
}

// Get current environment configuration
const CURRENT_ENV = detectEnvironment();
const ENV_CONFIG = ENV_CONFIGS[CURRENT_ENV];

// Expose environment control functions globally for console access
window.hyperplexityEnv = {
    set: setEnvironment,
    clear: clearEnvironmentPreference,
    current: () => CURRENT_ENV,
    available: () => Object.keys(ENV_CONFIGS),
    config: () => ENV_CONFIG
};

// ============================================
// CONFIGURATION
// ============================================
const API_BASE = ENV_CONFIG.apiBase;
const WEBSOCKET_API_URL = ENV_CONFIG.websocketUrl;

// ============================================
// DEFERRED EMAIL VALIDATION
// ============================================
// If true, show Get Started first and validate email when user selects an action
// If false, require email validation upfront (original behavior)
const DEFER_EMAIL_VALIDATION = true;

// ============================================
// GLOBAL STATE (Minimal)
// ============================================
const globalState = {
    email: '',
    sessionId: null,
    websockets: new Map(), // Track WebSocket connections by card ID
    cardCounter: 0,
    cardProgress: {}, // Track progress by card ID
    excelFileUploaded: false, // Track if Excel file has been uploaded to unified storage
    configStored: false, // Track if config has been stored
    hasInsufficientBalance: false, // Track when user has insufficient balance
    tickerMessages: [], // Priority queue for ticker messages
    activeCardId: null, // Track which card is currently processing (for ticker display)
    tickerInterval: null, // Interval for cycling ticker messages
    currentTickerIndex: 0, // Current message being displayed
    currentConfidenceScore: null, // Track current confidence score (0-100) for progress color
    confidenceScores: [], // Array of all confidence scores received during current validation
    currentValidationState: null, // Track if preview or full validation is running
    isProcessingConfig: false, // Track if config generation/refinement is in progress
    debounceTimers: new Map(), // Track debounce timers by function/card ID
    isNewUser: true, // Track if user is new (no prior validation history) - ALWAYS TRUE FOR NOW
    userAttemptedProcessing: false, // Track if user tried to process but was blocked by insufficient balance
    pendingProcessingTrigger: null, // Store function to trigger processing when balance is sufficient
    isReferenceCheck: false, // Track if current session is reference check mode (affects button display)

    // Deferred email validation state
    pendingActionAfterEmail: null,    // Callback to execute after email validation
    pendingActionDescription: null,   // Description for UI feedback (e.g., "create your table")

    // Workflow state tracking
    workflowPhase: 'initial', // initial, upload, config, preview, validating, completed
    processingState: {
        previewCompleted: false,
        validationCompleted: false,
        validationStartTime: null,
        previewStartTime: null,
        lastEstimatedCost: null,
        lastBalanceCheck: null
    }
};

// Expose globalState to window for testing and debugging
window.globalState = globalState;

// Reference check state for managing reference validation workflow
const referenceCheckState = {
    cardId: null,
    conversationId: null,
    submittedText: null,
    pdfId: null,
    pdfFilename: null,
    awaitingPdfSelection: false
};

// Helper function to ensure processingState is always properly initialized
function ensureProcessingState() {
    if (!globalState.processingState || typeof globalState.processingState !== 'object') {
        console.warn('[GLOBALSTATE] Reinitializing null/invalid processingState');
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

// ============================================
// EMAIL VALIDATION HELPERS
// ============================================

/**
 * Execute action after ensuring email is validated.
 * If email already validated, executes immediately.
 * If not validated, shows email card and stores action for later.
 *
 * @param {Function} action - Callback to execute after email validation
 * @param {string} description - Description for UI (e.g., "create your table")
 */
function requireEmailThen(action, description = 'continue') {
    // If email already validated, execute immediately
    const storedEmail = localStorage.getItem('validatedEmail');
    if (globalState.email || (storedEmail && storedEmail.includes('@'))) {
        if (!globalState.email && storedEmail) {
            globalState.email = storedEmail;
        }
        action();
        return;
    }

    // Store pending action for after email validation
    globalState.pendingActionAfterEmail = action;
    globalState.pendingActionDescription = description;

    console.log(`[EMAIL] Deferring action until email validated: ${description}`);

    // Show email validation card
    createEmailCard();
}

// ============================================
// TESTING UTILITIES
// ============================================
function checkForTestingOverrides() {
    const urlParams = new URLSearchParams(window.location.search);

    // Force new user mode for testing
    if (urlParams.get('force_new_user') === 'true') {
        globalState.isNewUser = true;
    }

    // Force returning user mode for testing
    if (urlParams.get('force_returning_user') === 'true') {
        globalState.isNewUser = false;
    }
}

// ============================================
// PAGE TYPE DETECTION
// ============================================
function detectPageType() {
    // Check URL for chex or reference-check parameter
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'chex' || urlParams.get('page') === 'chex' ||
        urlParams.get('mode') === 'reference-check' || urlParams.get('page') === 'reference-check') {
        return 'reference-check';
    }

    // Check page title
    const pageTitle = document.title.toLowerCase();
    if (pageTitle.includes('chex') || (pageTitle.includes('reference') && pageTitle.includes('check'))) {
        return 'reference-check';
    }

    // Check for URL path (chex or reference-check)
    if (window.location.pathname.includes('chex') || window.location.pathname.includes('reference-check')) {
        return 'reference-check';
    }

    // Default mode
    return 'default';
}

// Make testing functions available globally for console use
window.testingUtils = {
    forceNewUser: () => {
        globalState.isNewUser = true;
    },
    forceReturningUser: () => {
        globalState.isNewUser = false;
    },
    showDemoCard: () => {
        createSelectDemoCard();
    },
    showUploadOrDemoCard: () => {
        createUploadOrDemoCard();
    },
    checkNewUserStatus: () => {
        return globalState.isNewUser;
    },
    clearUserHistory: async (email = null) => {
        const userEmail = email || globalState.email;
        if (!userEmail) {
            console.error('[TESTING] No email provided and no current user email');
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'clearUserHistoryForTesting',
                    email: userEmail
                })
            });

            const result = await response.json();

            if (result.success) {
            } else {
                console.error(`[TESTING] Failed to clear history: ${result.error}`);
            }

            return result;
        } catch (error) {
            console.error('[TESTING] Error clearing user history:', error);
            return { success: false, error: error.message };
        }
    },
    // Quick test sequence
    testNewUserFlow: async () => {

        // Force new user mode
        globalState.isNewUser = true;

        // Show the choice card
        createUploadOrDemoCard();

    }
};

// ============================================
// ENVIRONMENT INDICATOR
// ============================================

// Add environment indicator to page (only show if not prod)
if (CURRENT_ENV !== 'prod') {
    const indicator = document.createElement('div');
    indicator.className = `environment-indicator ${CURRENT_ENV}`;
    indicator.textContent = CURRENT_ENV;
    indicator.title = `Environment: ${CURRENT_ENV}\nAPI: ${API_BASE}`;
    document.body.appendChild(indicator);
}

// ============================================
// MOBILE DETECTION
// ============================================

function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
        || window.innerWidth < 768;
}

function showMobileMessage() {
    const cardContainer = document.getElementById('cardContainer');
    cardContainer.innerHTML = `
        <div class="card" style="text-align: center; background: linear-gradient(135deg, #ff6b6b, #ee5a24); color: white;">
            <div style="padding: 3rem 2rem;">
                <div style="font-size: 4rem; margin-bottom: 1.5rem;">📱</div>
                <h1 style="color: white; margin-bottom: 1rem; font-size: 2rem;">You are on mobile</h1>
                <p style="font-size: 1.2rem; margin-bottom: 1rem; line-height: 1.6;">
                    Who does spreadsheet work on a phone?!
                </p>
                <p style="font-size: 1.1rem; margin-bottom: 1rem; line-height: 1.6;">
                    For now check out the gallery below.
                </p>
                <p style="font-size: 1.1rem; opacity: 0.9; line-height: 1.6;">
                    Get to a computer soon, and we will get this going together.
                </p>
                <p style="font-size: 1rem; opacity: 0.8; font-style: italic; margin-top: 1.5rem;">
                    -Management
                </p>
            </div>
        </div>
    `;
}

// ============================================
// CREDIT PURCHASING SYSTEM
// ============================================

/**
 * Add credits to cart using the product component on the page
 * @param {number} quantity - Number of credits to add
 * @returns {boolean} Success status
 */
function addCreditsToCart(quantity) {
    if (!quantity || quantity < 1) {
        console.warn('[CREDITS] Invalid quantity:', quantity);
        return false;
    }


    // Find the quantity input
    const quantityInput = document.querySelector('input[name="quantity-input"]');
    if (!quantityInput) {
        console.warn('[CREDITS] Quantity input not found. Make sure the product component is on the page.');
        return false;
    }

    // Find the add-to-cart button
    const addToCartButton = document.querySelector('.sqs-add-to-cart-button');
    if (!addToCartButton) {
        console.warn('[CREDITS] Add-to-cart button not found.');
        return false;
    }

    // Set the quantity
    quantityInput.value = quantity;

    // Trigger input events to make sure the UI updates
    const inputEvent = new Event('input', { bubbles: true });
    const changeEvent = new Event('change', { bubbles: true });
    quantityInput.dispatchEvent(inputEvent);
    quantityInput.dispatchEvent(changeEvent);

    // Click the add-to-cart button
    setTimeout(() => {
        addToCartButton.click();
    }, 500);

    return true;
}

/**
 * Add credits and redirect to cart page
 * @param {number} quantity - Number of credits to add
 */
function addCreditsAndGoToCart(quantity) {
    if (!quantity || quantity < 1) {
        console.warn('[CREDITS] Invalid quantity for purchase:', quantity);
        // Just go to cart if invalid quantity
        window.open('https://eliyahu.ai/cart', '_blank');
        return;
    }


    const success = addCreditsToCart(quantity);

    if (success) {
        // Wait for cart to update, then open cart in new tab
        setTimeout(() => {
            window.open('https://eliyahu.ai/cart', '_blank');
        }, 1500);
    } else {
        // Fallback: open cart in new tab
        window.open('https://eliyahu.ai/cart', '_blank');
    }
}

/**
 * Main function for when user needs credits
 * @param {number} quantity - Number of credits needed
 */
function needCredits(quantity) {
    addCreditsAndGoToCart(quantity);
}

/**
 * Check if the product component is available on the page
 * @returns {boolean} True if components are found
 */
function checkProductComponent() {
    const quantityInput = document.querySelector('input[name="quantity-input"]');
    const addButton = document.querySelector('.sqs-add-to-cart-button');
    const increaseBtn = document.querySelector('.increase-button');
    const decreaseBtn = document.querySelector('.decrease-button');


    if (quantityInput) {
    }

    return !!(quantityInput && addButton);
}

// Expose credit purchasing functions globally
window.creditPurchasing = {
    addToCart: addCreditsToCart,
    addAndGoToCart: addCreditsAndGoToCart,
    needCredits: needCredits,
    checkComponent: checkProductComponent
};

// Also expose individual functions for console use
window.needCredits = needCredits;
window.addCreditsToCart = addCreditsToCart;
window.addCreditsAndGoToCart = addCreditsAndGoToCart;
window.checkProductComponent = checkProductComponent;

// Check if product component is available on page load
setTimeout(() => {
    const componentAvailable = checkProductComponent();
    if (componentAvailable) {
    } else {
    }
}, 1000);
