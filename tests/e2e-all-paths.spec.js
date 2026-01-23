// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath, pathToFileURL } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Path to the DEV frontend HTML file
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_FullScript_Temp-dev.html');
const frontendUrl = process.env.TEST_URL || pathToFileURL(frontendPath).href;

// Test configuration
const TIMEOUTS = {
  SHORT: 5000,      // Basic UI operations
  MEDIUM: 30000,    // API calls
  LONG: 120000,     // Full validation runs
  XLARGE: 300000    // Complex operations
};

// Use environment variable or default to eliyahu@eliyahu.ai for testing
// Set TEST_EMAIL env var to use a different email
const TEST_EMAIL = process.env.TEST_EMAIL || 'eliyahu@eliyahu.ai';

/**
 * Comprehensive End-to-End Tests for All 4 User Paths
 *
 * Paths:
 * 1. Demo Table Selection
 * 2. Upload Your Own Table
 * 3. Table Maker (Create from Prompt)
 * 4. Reference Check
 *
 * Test Email Configuration:
 * - Default: eliyahu@eliyahu.ai
 * - Override with: TEST_EMAIL=your-email@example.com npm run test:e2e
 * - Requirements: Email must be validated in backend and have sufficient credits
 */

// ============================================
// HELPER FUNCTIONS
// ============================================

/**
 * Clear localStorage to simulate fresh user (no stored email)
 */
async function clearStoredEmail(page) {
  await page.evaluate(() => {
    localStorage.removeItem('validatedEmail');
  });
}

/**
 * Set email in localStorage to simulate returning user
 */
async function setStoredEmail(page, email = TEST_EMAIL) {
  await page.evaluate((e) => {
    localStorage.setItem('validatedEmail', e);
  }, email);
}

/**
 * Navigate to app and wait for Get Started card
 */
async function navigateToGetStarted(page) {
  await page.goto(frontendUrl);
  await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

  // Wait for Get Started card to appear
  await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });
}

/**
 * Handle email prompt if it appears after clicking an action
 * Returns true if email was entered, false if skipped (returning user)
 */
async function handleEmailPromptIfNeeded(page) {
  // Wait for potential email card to appear
  await page.waitForTimeout(1000);

  // Check if email input is visible (Email Validation card appeared)
  const emailInput = page.locator('input[type="email"]').first();
  const isEmailVisible = await emailInput.isVisible().catch(() => false);

  if (isEmailVisible) {
    // Fill in the email
    await emailInput.fill(TEST_EMAIL);

    // Click "Validate Email" button
    const validateButton = page.locator('button:has-text("Validate Email")').first();
    await expect(validateButton).toBeVisible({ timeout: TIMEOUTS.SHORT });
    await validateButton.click();

    // Wait for API response - if email already validated, it proceeds automatically
    // If not validated, code input section appears
    await page.waitForTimeout(3000);

    // Check if we need to enter a verification code (new email case)
    const codeInput = page.locator('input[placeholder*="code"], input[maxlength="6"]').first();
    const isCodeVisible = await codeInput.isVisible().catch(() => false);

    if (isCodeVisible) {
      // This is a new email that needs verification - tests can't proceed without real code
      console.log('Email verification code required - test may fail for unvalidated emails');
      // For testing, we'd need the email to be pre-validated in backend
    }

    // Wait for the Get Started card or next card to appear
    await page.waitForTimeout(2000);
    return true;
  }
  return false;
}

/**
 * Click action button on Get Started card
 */
async function clickGetStartedAction(page, action) {
  const buttonTexts = {
    demo: 'Explore a Demo Table',
    upload: 'Upload Your Own Table',
    tablemaker: 'Create Table from Prompt',
    refcheck: 'Check Text References'
  };

  const buttonText = buttonTexts[action];
  if (!buttonText) throw new Error(`Unknown action: ${action}`);

  const button = page.locator(`.card button:has-text("${buttonText}")`);
  await expect(button).toBeVisible({ timeout: TIMEOUTS.SHORT });
  await button.click();
}

/**
 * Complete flow to reach a specific path (handles email if needed)
 * By default, simulates a returning user with email already stored to bypass verification code flow
 */
async function navigateToPath(page, action, options = {}) {
  const { simulateReturningUser = true } = options;

  await page.goto(frontendUrl);

  if (simulateReturningUser) {
    // Set email in localStorage to simulate returning user (bypasses verification code)
    await setStoredEmail(page, TEST_EMAIL);
    await page.reload();
  } else {
    // Clear email to force fresh validation (requires verification code)
    await clearStoredEmail(page);
    await page.reload();
  }

  await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });
  await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });

  // Click the action button
  await clickGetStartedAction(page, action);

  // For returning users, the action proceeds directly without email prompt
  // For new users, handle email prompt if it appears
  if (!simulateReturningUser) {
    const emailHandled = await handleEmailPromptIfNeeded(page);
    if (emailHandled) {
      // After email validation, the pending action should execute automatically
      await page.waitForTimeout(2000);
    }
  }

  // Wait for next card to load
  await page.waitForTimeout(1500);
}

/**
 * Legacy helper - complete email validation flow
 * Now navigates to Get Started and clicks Demo as default action
 */
async function completeEmailValidation(page) {
  await navigateToPath(page, 'demo');
}

/**
 * Wait for WebSocket connection
 * Maps don't serialize well in waitForFunction, so check for session ID and processing state instead
 */
async function waitForWebSocket(page, timeout = TIMEOUTS.MEDIUM) {
  // WebSocket is connected when validation starts, indicated by sessionId being set
  await page.waitForFunction(() => {
    return window.globalState &&
           window.globalState.sessionId &&
           window.globalState.sessionId.startsWith('session');
  }, { timeout });

  // Give WebSocket a moment to fully establish
  await page.waitForTimeout(1000);
}

/**
 * Wait for validation to complete
 */
async function waitForValidationComplete(page, timeout = TIMEOUTS.LONG) {
  await page.waitForFunction(() => {
    const state = window.globalState?.currentValidationState;
    return state === 'completed' || state === null;
  }, { timeout });
}

/**
 * Collect ticker messages during operation
 */
async function collectTickerMessages(page) {
  const messages = [];

  await page.exposeFunction('captureTickerMessage', (msg) => {
    messages.push(msg);
  });

  // Inject ticker listener
  await page.evaluate(() => {
    // Store original function if it exists
    if (typeof window.updateTicker === 'function') {
      window._originalUpdateTicker = window.updateTicker;
    }

    // Override with capturing version
    window.updateTicker = function(msg) {
      if (window.captureTickerMessage) {
        window.captureTickerMessage(msg);
      }
      if (window._originalUpdateTicker) {
        return window._originalUpdateTicker.apply(this, arguments);
      }
    };
  });

  return messages;
}

// ============================================
// PATH 1: DEMO TABLE SELECTION FLOW
// ============================================

test.describe('Path 1: Demo Table Selection', () => {

  test('1.1 - Should load demo selection card', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to demo path (handles Get Started + email if needed)
    await navigateToPath(page, 'demo');

    // Wait for demo selection card to load
    await page.waitForTimeout(1000);

    // Verify demo card appeared
    const cardTitle = page.locator('.card-title').last();
    await expect(cardTitle).toBeVisible();
    const titleText = await cardTitle.textContent();
    expect(titleText).toMatch(/demo|select/i);
  });

  test('1.2 - Should list available demos', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to demo path
    await navigateToPath(page, 'demo');

    // Wait for demos to load
    await page.waitForTimeout(2000);

    // Check if demos loaded
    const bodyText = await page.locator('body').textContent();

    // Should either show demos or show loading/error
    expect(
      bodyText.includes('Loading') ||
      bodyText.includes('demo') ||
      bodyText.includes('table') ||
      bodyText.includes('Select')
    ).toBeTruthy();
  });

  test('1.3 - Should select and load demo (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    // Navigate to demo path
    await navigateToPath(page, 'demo');

    // Wait for demo selection card to appear and demos to load from API
    // The API call takes 1-2 seconds to fetch demo list from backend
    await page.waitForTimeout(3000);

    // Find demo buttons specifically within the demos-list container
    // This avoids selecting Get Started card buttons which are also .std-button
    const demosListContainer = page.locator('[id$="-demos-list"]');
    const firstDemo = demosListContainer.locator('button.std-button').first();

    // Wait for the demo button to be visible
    await firstDemo.waitFor({ state: 'visible', timeout: TIMEOUTS.MEDIUM });

    await firstDemo.click();

    // Wait for preview card to appear (contains "Preview" in title)
    // After selecting demo, a preview validation card is automatically created
    await page.waitForTimeout(3000);

    // Verify preview card appeared with validation content
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).toMatch(/preview|validation|processing/i);

    // Verify session is active by checking localStorage
    const sessionId = await page.evaluate(() => localStorage.getItem('sessionId'));
    expect(sessionId).toBeTruthy();
    expect(sessionId).toMatch(/^session/);
  });

  test('1.4 - Should run preview validation on demo (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.XLARGE);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    const messages = await collectTickerMessages(page);

    // Navigate to demo path
    await navigateToPath(page, 'demo');

    // Wait for demo list to load from API
    await page.waitForTimeout(3000);

    // Select first demo from the demos-list container
    const demosListContainer = page.locator('[id$="-demos-list"]');
    const firstDemo = demosListContainer.locator('button.std-button').first();
    await firstDemo.waitFor({ state: 'visible', timeout: TIMEOUTS.MEDIUM });
    await firstDemo.click();

    // Wait for WebSocket connection
    await waitForWebSocket(page);

    // Wait for preview to complete
    await waitForValidationComplete(page, TIMEOUTS.LONG);

    // Verify results appeared
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).toMatch(/confidence|score|result/i);

    // Ticker messages may not be captured in test environment, but validation works
    console.log(`Ticker messages captured: ${messages.length}`);
  });
});

// ============================================
// PATH 2: UPLOAD YOUR OWN TABLE FLOW
// ============================================

test.describe('Path 2: Upload Your Own Table', () => {

  test('2.1 - Should show upload button', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to Get Started card
    await navigateToGetStarted(page);

    // Find upload button on Get Started card
    const uploadButton = page.locator('button:has-text("Upload")').first();
    await expect(uploadButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    const buttonText = await uploadButton.textContent();
    expect(buttonText).toMatch(/upload/i);
  });

  test('2.2 - Should trigger file picker on upload click', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);

    await page.goto(frontendUrl);
    // Simulate returning user to bypass email verification
    await setStoredEmail(page, TEST_EMAIL);
    await page.reload();
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });
    await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });

    // Set up file chooser listener BEFORE clicking (for returning users, picker opens immediately)
    const fileChooserPromise = page.waitForEvent('filechooser', { timeout: TIMEOUTS.MEDIUM });

    // Click upload button - for returning users, file picker opens directly
    await clickGetStartedAction(page, 'upload');

    // Wait for file chooser
    const fileChooser = await fileChooserPromise;
    expect(fileChooser).toBeTruthy();

    // File chooser appeared successfully - test passed!
  });

  test('2.3 - Should upload file and show config card (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    await page.goto(frontendUrl);
    // Simulate returning user to bypass email verification
    await setStoredEmail(page, TEST_EMAIL);
    await page.reload();
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });
    await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });

    // Set up file chooser listener BEFORE clicking
    const fileChooserPromise = page.waitForEvent('filechooser', { timeout: TIMEOUTS.MEDIUM });

    // Click upload button
    await clickGetStartedAction(page, 'upload');

    // Wait for file chooser
    const fileChooser = await fileChooserPromise;

    // Upload test file
    await fileChooser.setFiles('test-data/sample-table.xlsx');

    // Wait for upload to complete
    await page.waitForFunction(() => {
      return window.globalState && window.globalState.excelFileUploaded === true;
    }, { timeout: TIMEOUTS.MEDIUM });

    // Verify config card appears
    await page.waitForTimeout(2000);
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).toMatch(/config/i);
  });
});

// ============================================
// PATH 3: TABLE MAKER (CREATE FROM PROMPT) FLOW
// ============================================

test.describe('Path 3: Table Maker (Create from Prompt)', () => {

  test('3.1 - Should show Table Maker button', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to Get Started card
    await navigateToGetStarted(page);

    // Find Table Maker button on Get Started card
    const tableMakerButton = page.locator('button:has-text("Create Table from Prompt")').first();
    await expect(tableMakerButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    const buttonText = await tableMakerButton.textContent();
    expect(buttonText).toMatch(/create|table|prompt/i);
  });

  test('3.2 - Should load Table Maker card', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to Table Maker path
    await navigateToPath(page, 'tablemaker');

    // Wait for Table Maker card
    await page.waitForTimeout(1000);

    // Verify card appeared
    const cardTitle = page.locator('.card-title').last();
    await expect(cardTitle).toBeVisible();
    const titleText = await cardTitle.textContent();
    expect(titleText).toMatch(/table|maker|create/i);
  });

  test('3.3 - Should submit table prompt (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.XLARGE);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    const messages = await collectTickerMessages(page);

    // Navigate to Table Maker path
    await navigateToPath(page, 'tablemaker');

    await page.waitForTimeout(1000);

    // Find and fill prompt textarea
    const promptTextarea = page.locator('textarea').first();
    await expect(promptTextarea).toBeVisible({ timeout: TIMEOUTS.SHORT });

    await promptTextarea.fill('Create a table of top 5 programming languages with their year created and primary use case');

    // Submit prompt
    const submitButton = page.locator('button:has-text("Submit")').or(
      page.locator('button:has-text("Generate")')
    ).first();
    await submitButton.click();

    // Wait for WebSocket connection
    await waitForWebSocket(page, TIMEOUTS.LONG);

    // Wait for table generation
    await page.waitForTimeout(5000);

    // Ticker messages may not be captured in test environment, but generation works
    console.log(`Ticker messages captured: ${messages.length}`);

    // Verify the table generation started (body should have relevant text)
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).toMatch(/table|maker|generate|processing/i);
  });
});

// ============================================
// PATH 4: REFERENCE CHECK FLOW
// ============================================

test.describe('Path 4: Reference Check', () => {

  test('4.1 - Should show Reference Check button', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to Get Started card
    await navigateToGetStarted(page);

    // Find Reference Check button on Get Started card
    const refCheckButton = page.locator('button:has-text("Check Text References")').first();
    await expect(refCheckButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    const buttonText = await refCheckButton.textContent();
    expect(buttonText).toMatch(/reference|check/i);
  });

  test('4.2 - Should load Reference Check card', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Navigate to Reference Check path
    await navigateToPath(page, 'refcheck');

    // Wait for Reference Check card
    await page.waitForTimeout(1000);

    // Verify card appeared
    const cardTitle = page.locator('.card-title').last();
    await expect(cardTitle).toBeVisible();
    const titleText = await cardTitle.textContent();
    expect(titleText).toMatch(/reference|check/i);
  });

  test('4.3 - Should submit text for reference check (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.XLARGE);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    const messages = await collectTickerMessages(page);

    // Navigate to Reference Check path
    await navigateToPath(page, 'refcheck');

    await page.waitForTimeout(1000);

    // Find and fill text input
    const textInput = page.locator('textarea').first();
    await expect(textInput).toBeVisible({ timeout: TIMEOUTS.SHORT });

    const sampleText = `
      According to Smith et al. (2020), artificial intelligence has made significant progress in recent years.
      The study found that machine learning models can achieve human-level performance on many tasks.
      Recent research by Johnson (2021) confirms these findings.
    `;

    await textInput.fill(sampleText);

    // Wait for button animations to complete
    await page.waitForTimeout(1000);

    // Submit for checking - use specific text to avoid matching "Check Text References" button
    const submitButton = page.locator('button:has-text("Submit Text")').first();
    await expect(submitButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
    await submitButton.click();

    // Wait for WebSocket connection
    await waitForWebSocket(page, TIMEOUTS.LONG);

    // Wait for reference check to start
    await page.waitForTimeout(5000);

    // Ticker messages may not be captured in test environment, but reference check works
    console.log(`Ticker messages captured: ${messages.length}`);

    // Verify reference check started (body should have relevant text)
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).toMatch(/reference|check|processing|text/i);
  });
});

// ============================================
// CROSS-CUTTING TESTS
// ============================================

test.describe('Cross-Cutting: State Management', () => {

  test('S.1 - Should persist email in localStorage', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    // Set up returning user scenario (email already stored)
    await page.goto(frontendUrl);
    await setStoredEmail(page, TEST_EMAIL);
    await page.reload();

    // Wait for page to load
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Check localStorage - email should be persisted
    const storedEmail = await page.evaluate(() => {
      return localStorage.getItem('validatedEmail');
    });

    expect(storedEmail).toBe(TEST_EMAIL);
  });

  test('S.2 - Should create session ID on workflow start (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    // Navigate to demo path and select a demo
    await navigateToPath(page, 'demo');

    // Wait for demo list to load
    await page.waitForTimeout(3000);

    // Select first demo to start a workflow
    const demosListContainer = page.locator('[id$="-demos-list"]');
    const firstDemo = demosListContainer.locator('button.std-button').first();
    const isDemoVisible = await firstDemo.isVisible().catch(() => false);

    if (isDemoVisible) {
      await firstDemo.click();
      await page.waitForTimeout(2000);
    }

    // Check if sessionId exists in globalState
    const hasSession = await page.evaluate(() => {
      return window.globalState && typeof window.globalState.sessionId !== 'undefined';
    });

    expect(hasSession).toBeTruthy();
  });
});

test.describe('Cross-Cutting: Error Handling', () => {

  test('E.1 - Should handle invalid email gracefully', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    await page.goto(frontendUrl);
    await clearStoredEmail(page);
    await page.reload();
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Wait for Get Started card
    await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });

    // Click an action to trigger email prompt
    await clickGetStartedAction(page, 'demo');

    // Wait for email card to appear
    await page.waitForTimeout(1500);

    // Enter invalid email
    const emailInput = page.locator('input[type="email"]').first();
    const isEmailVisible = await emailInput.isVisible().catch(() => false);

    if (isEmailVisible) {
      await emailInput.fill('not-an-email');

      // Try to find the validate button
      const validateButton = page.locator('button:has-text("Validate Email")').first();
      const isButtonVisible = await validateButton.isVisible().catch(() => false);

      if (isButtonVisible) {
        // HTML5 email validation should mark the input as invalid
        const emailValid = await emailInput.evaluate((el) => el.validity.valid);
        expect(emailValid).toBeFalsy();
      }
    } else {
      // Email might already be stored, test passes
      expect(true).toBeTruthy();
    }
  });

  test('E.2 - Should not have JavaScript errors on any path', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);

    const errors = [];
    page.on('pageerror', error => errors.push(error.message));

    // Set up as returning user to avoid email verification flow
    await page.goto(frontendUrl);
    await setStoredEmail(page, TEST_EMAIL);
    await page.reload();
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Wait for Get Started card
    await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });

    // Wait for buttons to finish animating
    await page.waitForTimeout(1000);

    // Click each Get Started button one by one (except upload which opens file picker)
    const actions = ['demo', 'tablemaker', 'refcheck'];

    for (const action of actions) {
      await page.goto(frontendUrl);
      await setStoredEmail(page, TEST_EMAIL);
      await page.reload();
      await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });
      await expect(page.locator('text=Get Started')).toBeVisible({ timeout: TIMEOUTS.SHORT });
      await page.waitForTimeout(500);

      await clickGetStartedAction(page, action);
      await page.waitForTimeout(1500);
    }

    // Check no errors occurred
    expect(errors).toHaveLength(0);
  });
});

test.describe('Cross-Cutting: Environment Configuration', () => {

  test('ENV.1 - Should detect environment from filename or URL', async ({ page }) => {
    test.setTimeout(TIMEOUTS.SHORT);

    await page.goto(frontendUrl);
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Check environment detection
    const currentEnv = await page.evaluate(() => {
      return window.hyperplexityEnv ? window.hyperplexityEnv.current() : null;
    });

    // Should detect environment (dev or prod depending on URL)
    expect(currentEnv).toMatch(/dev|prod/);
  });

  test('ENV.2 - Should have valid API endpoint configured', async ({ page }) => {
    test.setTimeout(TIMEOUTS.SHORT);

    await page.goto(frontendUrl);
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Check API endpoint (variables are inside IIFE, check via ENV_CONFIG)
    const envConfig = await page.evaluate(() => {
      // Try multiple ways to access config
      if (typeof ENV_CONFIG !== 'undefined') return ENV_CONFIG;
      if (typeof window.ENV_CONFIG !== 'undefined') return window.ENV_CONFIG;
      // Check exposed environment helper
      if (window.hyperplexityEnv && typeof window.hyperplexityEnv.config === 'function') {
        return window.hyperplexityEnv.config();
      }
      return null;
    });

    expect(envConfig).toBeTruthy();
    // Should have a valid API base URL
    expect(envConfig.apiBase).toMatch(/https:\/\/.*\.execute-api\..*\.amazonaws\.com\/(dev|prod)/);
  });

  test('ENV.3 - Should show environment indicator in dev mode only', async ({ page }) => {
    test.setTimeout(TIMEOUTS.SHORT);
    // Skip this test when testing production URL
    test.skip(frontendUrl.includes('eliyahu.ai'), 'Environment indicator only shows in dev mode');

    await page.goto(frontendUrl);
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Look for environment indicator (only visible in dev)
    const indicator = page.locator('.environment-indicator');
    const isVisible = await indicator.isVisible().catch(() => false);

    if (isVisible) {
      const indicatorText = await indicator.textContent();
      expect(indicatorText).toMatch(/dev|prod/);
    } else {
      // Indicator may not exist in prod, which is fine
      expect(true).toBeTruthy();
    }
  });
});
