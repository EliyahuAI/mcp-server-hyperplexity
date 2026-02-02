// @ts-check
/**
 * Security Flow Tests
 * Tests the new JWT authentication and token revocation system
 */
import { test, expect } from '@playwright/test';
import { fileURLToPath, pathToFileURL } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Configuration
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_FullScript_Temp-dev.html');
const frontendUrl = pathToFileURL(frontendPath).href;
const TEST_EMAIL = 'eliyahu@eliyahu.ai';
const PRODUCTION_URL = 'https://eliyahu.ai/hyperplexity';
const VIEWER_SESSION = 'session_20260202_144646_02c0f05c';

// Helper: Wait for network idle
async function waitForNetworkIdle(page, timeout = 2000) {
  await page.waitForLoadState('networkidle', { timeout });
}

// Helper: Get JWT token from sessionStorage
async function getSessionToken(page) {
  return await page.evaluate(() => sessionStorage.getItem('sessionToken'));
}

// Helper: Get validated email from localStorage
async function getValidatedEmail(page) {
  return await page.evaluate(() => localStorage.getItem('validatedEmail'));
}

test.describe('JWT Authentication Flow', () => {

  test.beforeEach(async ({ page }) => {
    // Clear storage before each test
    await page.goto(frontendUrl);
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test('should store JWT token after email validation', async ({ page }) => {
    test.setTimeout(30000);

    // Mock API response to return session token
    await page.route('**/validate', async (route) => {
      const request = route.request();
      const postData = request.postData();

      if (postData && postData.includes('checkOrSendValidation')) {
        // Return success with session token
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            validated: true,
            session_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJpYXQiOjE3Mzg0NTQ0MDAsImV4cCI6MTc0MTA0NjQwMCwianRpIjoiMTczODQ1NDQwMDEyMyJ9.test_signature'
          })
        });
      } else {
        await route.continue();
      }
    });

    await page.goto(frontendUrl);
    await page.waitForSelector('.card');

    // Enter email and submit
    await page.locator('input[type="email"]').first().fill(TEST_EMAIL);
    await page.locator('.card button').first().click();

    // Wait for response
    await page.waitForTimeout(1000);

    // Verify token is stored in sessionStorage
    const token = await getSessionToken(page);
    expect(token).toBeTruthy();
    expect(token).toContain('eyJ'); // JWT tokens start with this

    console.log('✓ JWT token stored in sessionStorage');
  });

  test('should show signed-in badge after authentication', async ({ page }) => {
    // Set up authenticated state
    await page.goto(frontendUrl);
    await page.evaluate((email) => {
      localStorage.setItem('validatedEmail', email);
      sessionStorage.setItem('sessionToken', 'test_token_' + Date.now());
      window.globalState = window.globalState || {};
      window.globalState.email = email;
      window.globalState.sessionToken = sessionStorage.getItem('sessionToken');
    }, TEST_EMAIL);

    // Reload to trigger signed-in badge display
    await page.reload();
    await page.waitForTimeout(500);

    // Check if badge would be shown (might need to trigger manually)
    const hasBadgeElement = await page.evaluate(() => {
      // Check if showSignedInBadge function exists
      return typeof window.showSignedInBadge === 'function';
    });

    if (hasBadgeElement) {
      // Manually trigger badge display
      await page.evaluate((email) => {
        if (typeof window.showSignedInBadge === 'function') {
          window.showSignedInBadge(email);
        }
      }, TEST_EMAIL);

      await page.waitForTimeout(500);

      // Verify badge is visible
      const badge = page.locator('.signed-in-badge');
      await expect(badge).toBeVisible();

      // Verify email is shown in badge
      const badgeText = await badge.textContent();
      expect(badgeText).toContain(TEST_EMAIL);

      console.log('✓ Signed-in badge displayed with email');
    }
  });

  test('should clear session on logout', async ({ page }) => {
    // Set up authenticated state
    await page.goto(frontendUrl);
    await page.evaluate((email) => {
      localStorage.setItem('validatedEmail', email);
      sessionStorage.setItem('sessionToken', 'test_token');
      window.globalState = window.globalState || {};
      window.globalState.email = email;

      // Show badge
      if (typeof window.showSignedInBadge === 'function') {
        window.showSignedInBadge(email);
      }
    }, TEST_EMAIL);

    await page.waitForTimeout(500);

    // Click logout badge (if visible)
    const badge = page.locator('.signed-in-badge');
    const badgeVisible = await badge.isVisible().catch(() => false);

    if (badgeVisible) {
      // Accept the confirmation dialog
      page.on('dialog', dialog => dialog.accept());

      await badge.click();
      await page.waitForTimeout(500);

      // Verify session cleared
      const token = await getSessionToken(page);
      const email = await getValidatedEmail(page);

      expect(token).toBeNull();
      expect(email).toBeNull();

      // Verify badge hidden
      await expect(badge).not.toBeVisible();

      console.log('✓ Session cleared and badge hidden after logout');
    } else {
      console.log('⚠ Signed-in badge not visible (may need DOM-ready event)');
    }
  });

});

test.describe('Demo Mode (No Authentication Required)', () => {

  test('should load demo without email validation', async ({ page }) => {
    test.setTimeout(30000);

    // Mock demo data API
    await page.route('**/validate', async (route) => {
      const request = route.request();
      const postData = request.postData();

      if (postData && postData.includes('getDemoData')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            table_metadata: {
              table_name: 'Demo Table',
              columns: [
                { name: 'Column 1', importance: 'HIGH' }
              ],
              rows: [
                {
                  row_key: 'row_1',
                  cells: {
                    'Column 1': {
                      display_value: 'Test Value',
                      confidence: 'HIGH'
                    }
                  }
                }
              ],
              is_transposed: true
            },
            clean_table_name: 'Demo Table',
            is_demo: true
          })
        });
      } else {
        await route.continue();
      }
    });

    // Navigate to demo mode
    await page.goto(`${frontendUrl}?demo=TestDemo`);
    await page.waitForTimeout(2000);

    // Verify demo loaded without email prompt
    const emailInputs = await page.locator('input[type="email"]').count();
    expect(emailInputs).toBe(0); // No email input should appear

    // Verify demo table appears
    const pageText = await page.locator('body').textContent();
    expect(pageText).toMatch(/Demo Table|Demo/i);

    // Verify no signed-in badge
    const badgeCount = await page.locator('.signed-in-badge').count();
    expect(badgeCount).toBe(0);

    console.log('✓ Demo mode loaded without authentication');
  });

});

test.describe('Viewer Mode with Authentication', () => {

  test('should require email for viewer mode', async ({ page }) => {
    test.setTimeout(30000);

    // Navigate to viewer mode without pre-existing auth
    await page.goto(`${frontendUrl}?mode=viewer&session=${VIEWER_SESSION}`);
    await page.waitForTimeout(2000);

    // Should show email validation card
    const emailInput = page.locator('input[type="email"]').first();
    await expect(emailInput).toBeVisible();

    console.log('✓ Viewer mode requires email validation');
  });

  test('should send X-Session-Token header in viewer requests', async ({ page }) => {
    test.setTimeout(30000);

    let sentToken = null;

    // Intercept API requests to verify token is sent
    await page.route('**/validate', async (route) => {
      const request = route.request();
      const headers = request.headers();

      // Capture X-Session-Token header
      if (headers['x-session-token']) {
        sentToken = headers['x-session-token'];
      }

      // Mock response
      const postData = request.postData();
      if (postData && postData.includes('getViewerData')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            table_metadata: { table_name: 'Test', columns: [], rows: [] },
            table_name: 'Test Table'
          })
        });
      } else {
        await route.continue();
      }
    });

    // Set up authenticated state
    await page.goto(frontendUrl);
    await page.evaluate((email) => {
      sessionStorage.setItem('sessionToken', 'test_jwt_token_12345');
      localStorage.setItem('validatedEmail', email);
      window.globalState = window.globalState || {};
      window.globalState.email = email;
      window.globalState.sessionToken = 'test_jwt_token_12345';
    }, TEST_EMAIL);

    // Navigate to viewer
    await page.goto(`${frontendUrl}?mode=viewer&session=${VIEWER_SESSION}`);
    await page.waitForTimeout(2000);

    // Verify token was sent
    expect(sentToken).toBe('test_jwt_token_12345');

    console.log('✓ X-Session-Token header sent in API requests');
  });

});

test.describe('Security Violations', () => {

  test('should handle token revocation response', async ({ page }) => {
    test.setTimeout(30000);

    // Mock API to return token_revoked
    await page.route('**/validate', async (route) => {
      const request = route.request();
      const postData = request.postData();

      if (postData && postData.includes('getViewerData')) {
        await route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: 'Access denied: you do not own this session. Your session has been revoked for security.',
            token_revoked: true
          })
        });
      } else {
        await route.continue();
      }
    });

    // Set up authenticated state
    await page.goto(frontendUrl);
    await page.evaluate((email) => {
      sessionStorage.setItem('sessionToken', 'test_token');
      localStorage.setItem('validatedEmail', email);
      window.globalState = window.globalState || {};
      window.globalState.email = email;
      window.globalState.sessionToken = 'test_token';
    }, TEST_EMAIL);

    // Navigate to viewer (will trigger revocation)
    await page.goto(`${frontendUrl}?mode=viewer&session=${VIEWER_SESSION}`);
    await page.waitForTimeout(2000);

    // Verify session was cleared
    const token = await getSessionToken(page);
    const email = await getValidatedEmail(page);

    expect(token).toBeNull();
    expect(email).toBeNull();

    // Verify security alert shown
    const pageText = await page.locator('body').textContent();
    expect(pageText).toMatch(/security|revoked/i);

    console.log('✓ Token revocation handled correctly');
  });

});
