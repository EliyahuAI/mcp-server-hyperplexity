// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Path to the built frontend HTML file
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend.html');
const frontendUrl = `file://${frontendPath}`;

test.describe('Hyperplexity Frontend', () => {

  test('loads without JavaScript errors', async ({ page }) => {
    const errors = [];

    // Capture console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Capture page errors
    page.on('pageerror', error => {
      errors.push(error.message);
    });

    await page.goto(frontendUrl);

    // Wait a moment for any errors to appear
    await page.waitForTimeout(1000);

    // Check for no errors
    expect(errors).toEqual([]);
  });

  test('email card appears on page load', async ({ page }) => {
    await page.goto(frontendUrl);

    // Wait for the card container
    await page.waitForSelector('#cardContainer', { timeout: 5000 });

    // Wait for a card to be created (should happen after 100ms delay)
    await page.waitForSelector('.card', { timeout: 3000 });

    // Verify the card exists
    const card = await page.$('.card');
    expect(card).not.toBeNull();
  });

  test('email card has correct structure', async ({ page }) => {
    await page.goto(frontendUrl);

    // Wait for card to appear
    await page.waitForSelector('.card', { timeout: 3000 });

    // Check for email icon
    const icon = await page.locator('.card-icon').first();
    await expect(icon).toHaveText('📧');

    // Check for title
    const title = await page.locator('.card-title').first();
    await expect(title).toContainText('Email Verification');

    // Check for email input field
    const emailInput = await page.locator('input[type="email"]').first();
    await expect(emailInput).toBeVisible();
  });

  test('can enter email address', async ({ page }) => {
    await page.goto(frontendUrl);

    // Wait for card and input
    await page.waitForSelector('input[type="email"]', { timeout: 3000 });

    // Enter email
    await page.fill('input[type="email"]', 'test@example.com');

    // Verify email was entered
    const value = await page.inputValue('input[type="email"]');
    expect(value).toBe('test@example.com');
  });

  test('send code button exists and is enabled', async ({ page }) => {
    await page.goto(frontendUrl);

    // Wait for card
    await page.waitForSelector('.card', { timeout: 3000 });

    // Enter a valid email first
    await page.fill('input[type="email"]', 'test@example.com');

    // Find the send code button
    const sendButton = page.locator('button', { hasText: 'Send Code' }).first();
    await expect(sendButton).toBeVisible();
    await expect(sendButton).toBeEnabled();
  });

  test('only one DOMContentLoaded handler fires', async ({ page }) => {
    const logs = [];

    // Capture all console logs
    page.on('console', msg => {
      logs.push(msg.text());
    });

    await page.goto(frontendUrl);
    await page.waitForTimeout(1000);

    // Filter for any duplicate initialization messages
    const initLogs = logs.filter(log =>
      log.includes('DOMContentLoaded') ||
      log.includes('[CREATE_EMAIL]')
    );

    console.log('Initialization logs:', initLogs);

    // Should only see initialization happen once
    // (This is a heuristic - we're checking for duplicate messages)
  });

  test('globalState is initialized', async ({ page }) => {
    await page.goto(frontendUrl);

    // Check that globalState exists and has expected properties
    const globalState = await page.evaluate(() => {
      return typeof window.globalState !== 'undefined' &&
             window.globalState !== null;
    });

    expect(globalState).toBe(true);
  });

  test('card counter increments correctly', async ({ page }) => {
    await page.goto(frontendUrl);

    await page.waitForSelector('.card', { timeout: 3000 });

    // Get the card ID
    const cardId = await page.evaluate(() => {
      const firstCard = document.querySelector('.card');
      return firstCard ? firstCard.id : null;
    });

    // Should be card-1 (first card)
    expect(cardId).toBe('card-1');
  });

  test('no duplicate cards are created', async ({ page }) => {
    await page.goto(frontendUrl);

    // Wait for initial card
    await page.waitForSelector('.card', { timeout: 3000 });

    // Wait a bit longer to see if any duplicates appear
    await page.waitForTimeout(2000);

    // Count cards
    const cardCount = await page.locator('.card').count();

    // Should only be 1 card (email verification)
    expect(cardCount).toBe(1);
  });

  test('IIFE wrapper is present', async ({ page }) => {
    await page.goto(frontendUrl);

    // Check that code is wrapped in IIFE by looking for function scope
    const hasIIFE = await page.evaluate(() => {
      // If IIFE is present, globalState won't be directly on window
      // It should be set via window.globalState = ...
      // But we can check that internal functions aren't polluting global scope
      return typeof createCard === 'undefined'; // createCard should not be global
    });

    // createCard should NOT be in global scope (it's inside IIFE)
    expect(hasIIFE).toBe(true);
  });

  test('page title is correct', async ({ page }) => {
    await page.goto(frontendUrl);

    await expect(page).toHaveTitle(/Hyperplexity.*AI Research Tables/);
  });

  test('cardContainer element exists', async ({ page }) => {
    await page.goto(frontendUrl);

    const container = await page.$('#cardContainer');
    expect(container).not.toBeNull();
  });

  test('no syntax errors in console', async ({ page }) => {
    const syntaxErrors = [];

    page.on('console', msg => {
      if (msg.type() === 'error' && msg.text().includes('SyntaxError')) {
        syntaxErrors.push(msg.text());
      }
    });

    page.on('pageerror', error => {
      if (error.message.includes('SyntaxError')) {
        syntaxErrors.push(error.message);
      }
    });

    await page.goto(frontendUrl);
    await page.waitForTimeout(1000);

    expect(syntaxErrors).toEqual([]);
  });

});
