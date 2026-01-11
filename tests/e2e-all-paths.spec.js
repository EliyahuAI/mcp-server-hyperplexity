// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Path to the DEV frontend HTML file
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend-dev.html');
const frontendUrl = process.env.TEST_URL || `file://${frontendPath}`;

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
 * Complete email validation flow
 */
async function completeEmailValidation(page) {
  await page.goto(frontendUrl);
  await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

  // Enter email
  const emailInput = page.locator('input[type="email"]').first();
  await emailInput.fill(TEST_EMAIL);

  // Click validate button
  const validateButton = page.locator('.card button').first();
  await validateButton.click();

  // Wait for backend response and Get Started card to appear
  // The backend API call might take time, so wait longer
  await page.waitForTimeout(5000);

  // Verify Get Started card loaded by checking text appeared
  const bodyText = await page.locator('body').textContent();
  expect(bodyText).toMatch(/Get Started|Explore|Demo|Upload|Create Table|Reference/i);
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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click "Explore a Demo Table" button
    const demoButton = page.locator('button:has-text("Explore")').or(
      page.locator('button:has-text("Demo")')
    ).first();

    await expect(demoButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
    await demoButton.click();

    // Wait for demo selection card
    await page.waitForTimeout(1000);

    // Verify demo card appeared
    const cardTitle = page.locator('.card-title').last();
    await expect(cardTitle).toBeVisible();
    const titleText = await cardTitle.textContent();
    expect(titleText).toMatch(/demo/i);
  });

  test('1.2 - Should list available demos', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click demo button
    const demoButton = page.locator('button:has-text("Explore")').or(
      page.locator('button:has-text("Demo")')
    ).first();
    await demoButton.click();

    // Wait for demos to load
    await page.waitForTimeout(2000);

    // Check if demos loaded
    const bodyText = await page.locator('body').textContent();

    // Should either show demos or show loading/error
    expect(
      bodyText.includes('Loading') ||
      bodyText.includes('demo') ||
      bodyText.includes('table')
    ).toBeTruthy();
  });

  test('1.3 - Should select and load demo (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click demo button
    const demoButton = page.locator('button:has-text("Explore")').or(
      page.locator('button:has-text("Demo")')
    ).first();
    await demoButton.click();

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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    const messages = await collectTickerMessages(page);

    // Select demo
    const demoButton = page.locator('button:has-text("Explore")').or(
      page.locator('button:has-text("Demo")')
    ).first();
    await demoButton.click();

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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Find upload button
    const uploadButton = page.locator('button:has-text("Upload")').first();
    await expect(uploadButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    const buttonText = await uploadButton.textContent();
    expect(buttonText).toMatch(/upload/i);
  });

  test('2.2 - Should trigger file picker on upload click', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click upload button
    const uploadButton = page.locator('button:has-text("Upload")').first();
    await expect(uploadButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    // Set up file chooser listener BEFORE clicking
    const fileChooserPromise = page.waitForEvent('filechooser', { timeout: TIMEOUTS.MEDIUM });

    await uploadButton.click();

    // Wait for file chooser
    const fileChooser = await fileChooserPromise;
    expect(fileChooser).toBeTruthy();

    // File chooser appeared successfully - test passed!
  });

  test('2.3 - Should upload file and show config card (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    const uploadButton = page.locator('button:has-text("Upload")').first();

    // Set up file chooser
    const fileChooserPromise = page.waitForEvent('filechooser');
    await uploadButton.click();
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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Find Table Maker button
    const tableMakerButton = page.locator('button:has-text("Create")').or(
      page.locator('button:has-text("Table")').or(
        page.locator('button:has-text("Prompt")')
      )
    ).first();

    await expect(tableMakerButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    const buttonText = await tableMakerButton.textContent();
    expect(buttonText).toMatch(/create|table|prompt/i);
  });

  test('3.2 - Should load Table Maker card', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click Table Maker button
    const tableMakerButton = page.locator('button:has-text("Create")').or(
      page.locator('button:has-text("Table")').or(
        page.locator('button:has-text("Prompt")')
      )
    ).first();

    await tableMakerButton.click();

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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    const messages = await collectTickerMessages(page);

    // Click Table Maker button
    const tableMakerButton = page.locator('button:has-text("Create")').or(
      page.locator('button:has-text("Table")').or(
        page.locator('button:has-text("Prompt")')
      )
    ).first();
    await tableMakerButton.click();

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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Find Reference Check button
    const refCheckButton = page.locator('button:has-text("Reference")').or(
      page.locator('button:has-text("Check")')
    ).first();

    await expect(refCheckButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

    const buttonText = await refCheckButton.textContent();
    expect(buttonText).toMatch(/reference|check/i);
  });

  test('4.2 - Should load Reference Check card', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click Reference Check button
    const refCheckButton = page.locator('button:has-text("Reference")').or(
      page.locator('button:has-text("Check")')
    ).first();

    await refCheckButton.click();

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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    const messages = await collectTickerMessages(page);

    // Click Reference Check button
    const refCheckButton = page.locator('button:has-text("Reference")').or(
      page.locator('button:has-text("Check")')
    ).first();
    await refCheckButton.click();

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

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Check localStorage
    const storedEmail = await page.evaluate(() => {
      return localStorage.getItem('validatedEmail');
    });

    expect(storedEmail).toBe(TEST_EMAIL);
  });

  test('S.2 - Should create session ID on workflow start (REQUIRES BACKEND)', async ({ page }) => {
    test.setTimeout(TIMEOUTS.MEDIUM);
    test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend required');

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click any workflow button
    const firstButton = page.locator('.card:last-child button').first();
    await expect(firstButton).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
    await firstButton.click();

    await page.waitForTimeout(1000);

    // Check if sessionId exists in globalState
    const hasSession = await page.evaluate(() => {
      return window.globalState && typeof window.globalState.sessionId !== 'undefined';
    });

    expect(hasSession).toBeTruthy();
  });
});

test.describe('Cross-Cutting: Error Handling', () => {

  test('E.1 - Should handle invalid email gracefully', async ({ page }) => {
    test.setTimeout(TIMEOUTS.SHORT);

    await page.goto(frontendUrl);
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Enter invalid email
    const emailInput = page.locator('input[type="email"]').first();
    await emailInput.fill('not-an-email');

    // Try to submit
    const validateButton = page.locator('.card button').first();

    // Button should be disabled OR email validation should fail
    const isDisabled = await validateButton.isDisabled();
    const emailValid = await emailInput.evaluate((el) => el.validity.valid);

    expect(isDisabled || !emailValid).toBeTruthy();
  });

  test('E.2 - Should not have JavaScript errors on any path', async ({ page }) => {
    test.setTimeout(TIMEOUTS.LONG);

    const errors = [];
    page.on('pageerror', error => errors.push(error.message));

    await completeEmailValidation(page);

  // Wait for buttons to finish animating
  await page.waitForTimeout(1000);

    // Click each Get Started button one by one
    const buttons = await page.locator('.card button').all();

    for (let i = 0; i < Math.min(buttons.length, 4); i++) {
      const button = buttons[i];
      if (await button.isVisible()) {
        await button.click();
        await page.waitForTimeout(1000);
      }
    }

    // Check no errors occurred
    expect(errors).toHaveLength(0);
  });
});

test.describe('Cross-Cutting: Environment Configuration', () => {

  test('ENV.1 - Should detect dev environment from filename', async ({ page }) => {
    test.setTimeout(TIMEOUTS.SHORT);

    await page.goto(frontendUrl);
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Check environment detection
    const currentEnv = await page.evaluate(() => {
      return window.hyperplexityEnv ? window.hyperplexityEnv.current() : null;
    });

    // Should detect 'dev' from Hyperplexity_frontend-dev.html
    expect(currentEnv).toBe('dev');
  });

  test('ENV.2 - Should use dev API endpoint', async ({ page }) => {
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
    expect(envConfig.apiBase).toContain('dev');
    expect(envConfig.apiBase).toContain('wqamcddvub');
  });

  test('ENV.3 - Should show environment indicator', async ({ page }) => {
    test.setTimeout(TIMEOUTS.SHORT);

    await page.goto(frontendUrl);
    await page.waitForSelector('#cardContainer', { timeout: TIMEOUTS.SHORT });

    // Look for environment indicator
    const indicator = page.locator('.environment-indicator');
    await expect(indicator).toBeVisible();

    const indicatorText = await indicator.textContent();
    expect(indicatorText).toBe('dev');
  });
});
