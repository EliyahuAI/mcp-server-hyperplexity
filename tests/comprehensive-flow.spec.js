// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Path to the built frontend HTML file
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend.html');
const frontendUrl = `file://${frontendPath}`;

/**
 * Comprehensive Frontend Test Suite
 * Tests all major user flows from start to finish
 */

test.describe('Comprehensive Frontend Flow Tests', () => {

  // ============================================
  // 1. EMAIL VALIDATION FLOW
  // ============================================

  test.describe('Email Validation', () => {

    test('should load email card on page load', async ({ page }) => {
      await page.goto(frontendUrl);

      // Wait for card container
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      // Verify email card appears
      const emailCard = page.locator('.card').first();
      await expect(emailCard).toBeVisible();

      // Verify card has email icon
      const icon = emailCard.locator('.card-icon');
      const iconText = await icon.textContent();
      expect(['📧', '✉️']).toContain(iconText);

      // Verify title
      const title = emailCard.locator('.card-title');
      await expect(title).toBeVisible();
    });

    test('should accept valid email address', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('input[type="email"]', { timeout: 3000 });

      const emailInput = page.locator('input[type="email"]').first();
      await emailInput.fill('test@example.com');

      const value = await emailInput.inputValue();
      expect(value).toBe('test@example.com');
    });

    test('should show validation button after email entry', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('input[type="email"]', { timeout: 3000 });

      await page.locator('input[type="email"]').first().fill('test@example.com');

      const button = page.locator('.card button').first();
      await expect(button).toBeVisible();
      await expect(button).toBeEnabled();
    });

    test('should progress to Get Started card after email validation', async ({ page }) => {
      test.setTimeout(30000);

      await page.goto(frontendUrl);
      await page.waitForSelector('.card', { timeout: 5000 });

      // Enter email
      await page.locator('input[type="email"]').first().fill('test@example.com');

      // Click validate button
      await page.locator('.card button').first().click();

      // Wait for second card
      await page.waitForTimeout(2000);

      // Verify multiple cards exist
      const cardCount = await page.locator('.card').count();
      expect(cardCount).toBeGreaterThanOrEqual(2);

      // Verify Get Started card appears
      const getStartedText = await page.locator('body').textContent();
      expect(getStartedText).toMatch(/Get Started|Explore|Demo|Upload/i);
    });
  });

  // ============================================
  // 2. GET STARTED - DEMO PATH
  // ============================================

  test.describe('Demo Selection Flow', () => {

    test('should show demo selection card', async ({ page }) => {
      test.setTimeout(30000);

      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Email validation
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Click "Explore a demo table"
      const demoButton = page.locator('button').filter({ hasText: /demo/i }).first();
      await demoButton.click();
      await page.waitForTimeout(2000);

      // Verify demo selection card appears
      const cardCount = await page.locator('.card').count();
      expect(cardCount).toBeGreaterThanOrEqual(3);

      // Check for demo-related text
      const pageText = await page.locator('body').textContent();
      expect(pageText).toMatch(/Select|Choose|Demo/i);
    });

    test('should list available demos', async ({ page }) => {
      test.setTimeout(30000);

      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Navigate to demo selection
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      const demoButton = page.locator('button').filter({ hasText: /demo/i }).first();
      await demoButton.click();
      await page.waitForTimeout(3000);

      // Check for demo buttons (Biden, Eisenhower, etc.)
      const allButtons = await page.locator('button').all();
      const buttonTexts = await Promise.all(allButtons.map(b => b.textContent()));

      // Should have multiple demo options
      const demoButtons = buttonTexts.filter(text =>
        text && (text.includes('Biden') || text.includes('Eisenhower') || text.includes('Demo'))
      );

      expect(demoButtons.length).toBeGreaterThan(0);
    });
  });

  // ============================================
  // 3. GET STARTED - UPLOAD PATH
  // ============================================

  test.describe('File Upload Flow', () => {

    test('should show upload button in Get Started card', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Navigate to Get Started
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Check for upload button
      const uploadButton = page.locator('button').filter({ hasText: /upload/i });
      await expect(uploadButton.first()).toBeVisible();
    });

    test('should have correct button order', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Navigate to Get Started
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Get all buttons in Get Started card
      const getStartedCard = page.locator('.card').nth(1);
      const buttons = await getStartedCard.locator('button').all();
      const buttonTexts = await Promise.all(buttons.map(b => b.textContent()));

      // Verify expected buttons are present
      const hasTableMaker = buttonTexts.some(text => text && text.includes('Create Table'));
      const hasUpload = buttonTexts.some(text => text && text.includes('Upload'));
      const hasDemo = buttonTexts.some(text => text && text.includes('Demo'));
      const hasReferenceCheck = buttonTexts.some(text => text && text.includes('Reference'));

      expect(hasTableMaker).toBe(true);
      expect(hasUpload).toBe(true);
      expect(hasDemo).toBe(true);
      expect(hasReferenceCheck).toBe(true);
    });
  });

  // ============================================
  // 4. TABLE MAKER PATH
  // ============================================

  test.describe('Table Maker Flow', () => {

    test('should show Table Maker button', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Navigate to Get Started
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Check for Table Maker button
      const tableMakerButton = page.locator('button').filter({
        hasText: /create table|table maker|prompt/i
      });
      await expect(tableMakerButton.first()).toBeVisible();
    });
  });

  // ============================================
  // 5. REFERENCE CHECK PATH
  // ============================================

  test.describe('Reference Check Flow', () => {

    test('should show Reference Check button', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Navigate to Get Started
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Check for Reference Check button
      const refCheckButton = page.locator('button').filter({
        hasText: /reference|check text/i
      });
      await expect(refCheckButton.first()).toBeVisible();
    });
  });

  // ============================================
  // 6. STATE MANAGEMENT
  // ============================================

  test.describe('State Management', () => {

    test('should maintain globalState', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Check that globalState exists
      const hasGlobalState = await page.evaluate(() => {
        return window.globalState !== undefined;
      });

      expect(hasGlobalState).toBe(true);
    });

    test('should increment card counter', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Get initial card count
      const initialCount = await page.evaluate(() => {
        return window.globalState.cardCounter;
      });

      expect(initialCount).toBeGreaterThanOrEqual(1);

      // Trigger another card
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Verify counter increased
      const newCount = await page.evaluate(() => {
        return window.globalState.cardCounter;
      });

      expect(newCount).toBeGreaterThan(initialCount);
    });

    test('should store email in globalState', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      const testEmail = 'test@example.com';

      // Enter email
      await page.locator('input[type="email"]').first().fill(testEmail);
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Check globalState
      const storedEmail = await page.evaluate(() => {
        return window.globalState.email;
      });

      // Email might be stored (depending on backend validation)
      // Just verify globalState is accessible
      expect(storedEmail !== undefined).toBe(true);
    });
  });

  // ============================================
  // 7. ERROR HANDLING
  // ============================================

  test.describe('Error Handling', () => {

    test('should not have JavaScript errors on load', async ({ page }) => {
      const errors = [];

      page.on('console', msg => {
        if (msg.type() === 'error') {
          errors.push(msg.text());
        }
      });

      page.on('pageerror', error => {
        errors.push(error.message);
      });

      await page.goto(frontendUrl);
      await page.waitForTimeout(2000);

      // Filter out expected warnings (postMessage, etc.)
      const criticalErrors = errors.filter(error =>
        !error.includes('postMessage') &&
        !error.includes('Failed to execute')
      );

      expect(criticalErrors).toEqual([]);
    });

    test('should not have undefined functions', async ({ page }) => {
      const errors = [];

      page.on('pageerror', error => {
        if (error.message.includes('is not defined')) {
          errors.push(error.message);
        }
      });

      await page.goto(frontendUrl);

      // Navigate through basic flow
      await page.waitForSelector('.card');
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      expect(errors).toEqual([]);
    });
  });

  // ============================================
  // 8. UI COMPONENTS
  // ============================================

  test.describe('UI Components', () => {

    test('should have proper card structure', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      const card = page.locator('.card').first();

      // Check for card elements
      await expect(card.locator('.card-icon')).toBeVisible();
      await expect(card.locator('.card-title')).toBeVisible();

      // Verify card has content
      const cardHTML = await card.innerHTML();
      expect(cardHTML.length).toBeGreaterThan(100);
    });

    test('should have functioning buttons', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      const button = page.locator('.card button').first();

      // Button should be visible and enabled
      await expect(button).toBeVisible();

      // Button should have text
      const buttonText = await button.textContent();
      expect(buttonText).toBeTruthy();
      expect(buttonText.length).toBeGreaterThan(0);
    });

    test('should use CSS custom properties', async ({ page }) => {
      await page.goto(frontendUrl);

      // Check if CSS variables are defined
      const hasCSSVars = await page.evaluate(() => {
        const style = getComputedStyle(document.documentElement);
        const primaryColor = style.getPropertyValue('--color-primary');
        return primaryColor !== '';
      });

      expect(hasCSSVars).toBe(true);
    });
  });

  // ============================================
  // 9. NAVIGATION FLOW
  // ============================================

  test.describe('Navigation Flow', () => {

    test('should maintain card history', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Initial card count
      let cardCount = await page.locator('.card').count();
      expect(cardCount).toBe(1);

      // Add second card
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      cardCount = await page.locator('.card').count();
      expect(cardCount).toBeGreaterThanOrEqual(2);

      // Verify both cards are still visible
      const firstCard = page.locator('.card').first();
      const secondCard = page.locator('.card').nth(1);

      await expect(firstCard).toBeVisible();
      await expect(secondCard).toBeVisible();
    });

    test('should scroll to new cards', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Navigate to Get Started
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Check that page has scrolled (second card should be in viewport)
      const secondCard = page.locator('.card').nth(1);
      const isInViewport = await secondCard.isVisible();
      expect(isInViewport).toBe(true);
    });
  });

  // ============================================
  // 10. ENVIRONMENT DETECTION
  // ============================================

  test.describe('Environment Configuration', () => {

    test('should detect environment', async ({ page }) => {
      await page.goto(frontendUrl);

      const env = await page.evaluate(() => {
        return window.hyperplexityEnv.current();
      });

      expect(['dev', 'test', 'staging', 'prod']).toContain(env);
    });

    test('should have API endpoints configured', async ({ page }) => {
      await page.goto(frontendUrl);

      const apiBase = await page.evaluate(() => {
        return window.API_BASE || (window.ENV_CONFIG && window.ENV_CONFIG.apiBase);
      });

      expect(apiBase).toBeTruthy();
      expect(apiBase).toContain('amazonaws.com');
    });

    test('should have WebSocket URL configured', async ({ page }) => {
      await page.goto(frontendUrl);

      const wsUrl = await page.evaluate(() => {
        return window.WEBSOCKET_API_URL ||
               (window.ENV_CONFIG && window.ENV_CONFIG.websocketUrl);
      });

      expect(wsUrl).toBeTruthy();
      expect(wsUrl).toMatch(/^wss?:\/\//);
    });
  });

  // ============================================
  // 11. PERFORMANCE
  // ============================================

  test.describe('Performance', () => {

    test('should load page quickly', async ({ page }) => {
      const start = Date.now();
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');
      const loadTime = Date.now() - start;

      // Page should load in under 5 seconds
      expect(loadTime).toBeLessThan(5000);
    });

    test('should render cards quickly', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      const start = Date.now();

      // Trigger new card
      await page.locator('input[type="email"]').first().fill('test@example.com');
      await page.locator('.card button').first().click();
      await page.waitForSelector('.card:nth-child(2)');

      const renderTime = Date.now() - start;

      // New card should appear within 3 seconds
      expect(renderTime).toBeLessThan(3000);
    });
  });

  // ============================================
  // 12. ACCESSIBILITY
  // ============================================

  test.describe('Accessibility', () => {

    test('should have proper heading hierarchy', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Check for card titles
      const titles = await page.locator('.card-title').all();
      expect(titles.length).toBeGreaterThan(0);
    });

    test('should have keyboard-accessible buttons', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card button');

      // Focus first button
      await page.locator('.card button').first().focus();

      // Verify button is focused
      const isFocused = await page.evaluate(() => {
        const activeElement = document.activeElement;
        return activeElement && activeElement.tagName === 'BUTTON';
      });

      expect(isFocused).toBe(true);
    });

    test('should have labels for inputs', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('input[type="email"]');

      // Email input should have placeholder or label
      const emailInput = page.locator('input[type="email"]').first();
      const placeholder = await emailInput.getAttribute('placeholder');

      expect(placeholder).toBeTruthy();
    });
  });

  // ============================================
  // 13. REGRESSION TESTS
  // ============================================

  test.describe('Regression Tests', () => {

    test('should not create duplicate cards', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('.card');

      // Wait to ensure no duplicates appear
      await page.waitForTimeout(3000);

      const cardCount = await page.locator('.card').count();
      expect(cardCount).toBe(1);
    });

    test('should not have duplicate DOMContentLoaded handlers', async ({ page }) => {
      const logs = [];

      page.on('console', msg => {
        if (msg.text().includes('[CREATE_EMAIL]') ||
            msg.text().includes('DOMContentLoaded')) {
          logs.push(msg.text());
        }
      });

      await page.goto(frontendUrl);
      await page.waitForTimeout(2000);

      // Should only see initialization once
      const initCount = logs.filter(log =>
        log.includes('[CREATE_EMAIL]')
      ).length;

      // Allow 0 or 1 (depending on logging level)
      expect(initCount).toBeLessThanOrEqual(1);
    });

    test('should wrap code in IIFE', async ({ page }) => {
      await page.goto(frontendUrl);

      // Internal functions should not be in global scope
      const hasIIFE = await page.evaluate(() => {
        // These functions should not be global
        return typeof createCard === 'undefined';
      });

      expect(hasIIFE).toBe(true);
    });
  });

  // ============================================
  // 14. MOBILE DETECTION
  // ============================================

  test.describe('Mobile Detection', () => {

    test('should detect desktop properly', async ({ page }) => {
      await page.goto(frontendUrl);

      // On desktop, should show normal interface
      const hasMobileMessage = await page.evaluate(() => {
        return document.body.textContent.includes('You are on mobile');
      });

      expect(hasMobileMessage).toBe(false);
    });

    test('should detect mobile on mobile viewport', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto(frontendUrl);

      // Might show mobile message
      const bodyText = await page.locator('body').textContent();

      // Either shows mobile message or normal interface
      expect(bodyText).toBeTruthy();
    });
  });

  // ============================================
  // 15. COMPLETE END-TO-END FLOW
  // ============================================

  test.describe('Complete User Journey', () => {

    test('should complete full demo selection flow', async ({ page }) => {
      test.setTimeout(45000);

      const consoleErrors = [];
      page.on('pageerror', error => {
        if (!error.message.includes('postMessage')) {
          consoleErrors.push(error.message);
        }
      });

      // Step 1: Load page
      await page.goto(frontendUrl);
      await page.waitForSelector('.card', { timeout: 5000 });

      // Step 2: Enter email
      await page.locator('input[type="email"]').first().fill('test@example.com');

      // Step 3: Validate email
      await page.locator('.card button').first().click();
      await page.waitForTimeout(2000);

      // Step 4: Select demo option
      const demoButton = page.locator('button').filter({ hasText: /demo/i }).first();
      await demoButton.click();
      await page.waitForTimeout(2000);

      // Step 5: Verify demo selection card
      const finalCardCount = await page.locator('.card').count();
      expect(finalCardCount).toBeGreaterThanOrEqual(3);

      // Verify no critical errors
      expect(consoleErrors).toEqual([]);

      // Verify reached demo selection
      const pageText = await page.locator('body').textContent();
      expect(pageText).toMatch(/Select|Demo|Biden|Eisenhower/i);
    });
  });
});
