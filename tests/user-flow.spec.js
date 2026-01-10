// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Path to the built frontend HTML file
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend.html');
const frontendUrl = `file://${frontendPath}`;

test.describe('User Flow: Email to Demo Selection', () => {

  test('complete flow from email entry to demo selection', async ({ page }) => {
    // Set longer timeout for this flow
    test.setTimeout(30000);

    // Capture console logs for debugging
    const consoleLogs = [];
    page.on('console', msg => {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    });

    // Capture errors
    const errors = [];
    page.on('pageerror', error => {
      errors.push(error.message);
    });

    // Step 1: Load the page
    console.log('Step 1: Loading page...');
    await page.goto(frontendUrl);
    await page.waitForSelector('.card', { timeout: 5000 });
    console.log('✓ Page loaded, email card visible');

    // Step 2: Enter email address
    console.log('Step 2: Entering email...');
    const emailInput = page.locator('input[type="email"]').first();
    await emailInput.fill('eliyahu@eliyahu.ai');
    console.log('✓ Email entered: eliyahu@eliyahu.ai');

    // Step 3: Click the button (should be "Send Code" or similar)
    console.log('Step 3: Looking for button...');

    // Wait a moment to ensure button is ready
    await page.waitForTimeout(500);

    // Find all buttons in the card
    const buttons = await page.locator('.card button').all();
    console.log(`Found ${buttons.length} button(s) in email card`);

    // Get button text for debugging
    for (let i = 0; i < buttons.length; i++) {
      const buttonText = await buttons[i].textContent();
      console.log(`  Button ${i}: "${buttonText}"`);
    }

    // Click the first button
    const firstButton = page.locator('.card button').first();
    const buttonText = await firstButton.textContent();
    console.log(`Clicking button: "${buttonText}"`);
    await firstButton.click();
    console.log('✓ Button clicked');

    // Step 4: Wait for the next card to appear (Get Started card)
    console.log('Step 4: Waiting for Get Started card...');

    // Wait for a second card to appear or for the first card to update
    await page.waitForTimeout(2000);

    // Count cards
    const cardCount = await page.locator('.card').count();
    console.log(`Current card count: ${cardCount}`);

    // Look for "Get Started" or similar text
    const pageContent = await page.content();
    const hasGetStarted = pageContent.includes('Get Started') ||
                          pageContent.includes('Explore') ||
                          pageContent.includes('Demo');
    console.log(`Has Get Started/Explore/Demo text: ${hasGetStarted}`);

    // Try to find buttons with "demo" or "explore" text
    const demoButtons = page.locator('button').filter({
      hasText: /demo|explore/i
    });
    const demoButtonCount = await demoButtons.count();
    console.log(`Found ${demoButtonCount} button(s) with demo/explore text`);

    if (demoButtonCount > 0) {
      // Step 5: Click "Explore a demo table" button
      console.log('Step 5: Clicking "Explore a demo table" button...');
      const exploreButton = page.locator('button').filter({
        hasText: /demo/i
      }).first();
      const exploreButtonText = await exploreButton.textContent();
      console.log(`Clicking: "${exploreButtonText}"`);
      await exploreButton.click();
      console.log('✓ Demo button clicked');

      // Step 6: Wait for demo selection card
      console.log('Step 6: Waiting for demo selection card...');
      await page.waitForTimeout(2000);

      // Check for demo selection options
      const finalCardCount = await page.locator('.card').count();
      console.log(`Final card count: ${finalCardCount}`);

      // Look for demo options (e.g., Biden, Eisenhower, etc.)
      const hasDemoOptions = await page.evaluate(() => {
        const text = document.body.textContent || '';
        return text.includes('Select') ||
               text.includes('Choose') ||
               text.includes('Demo') ||
               text.includes('Biden') ||
               text.includes('Eisenhower');
      });
      console.log(`Has demo selection options: ${hasDemoOptions}`);

      expect(hasDemoOptions).toBe(true);
      console.log('✓ Demo selection card appeared!');
    } else {
      console.log('⚠ No demo/explore button found - checking current state');

      // Get all visible text on the page
      const allText = await page.locator('body').textContent();
      console.log('Current page text (first 500 chars):');
      console.log(allText?.substring(0, 500));

      // List all buttons currently visible
      const allButtons = await page.locator('button').all();
      console.log(`\nAll visible buttons (${allButtons.length}):`);
      for (let i = 0; i < allButtons.length; i++) {
        const text = await allButtons[i].textContent();
        const isVisible = await allButtons[i].isVisible();
        console.log(`  ${i}: "${text}" (visible: ${isVisible})`);
      }
    }

    // Print console logs if there were errors
    if (errors.length > 0) {
      console.log('\n=== ERRORS ===');
      errors.forEach(err => console.log(err));
    }

    // Print relevant console logs
    console.log('\n=== CONSOLE LOGS ===');
    consoleLogs.forEach(log => console.log(log));

    // Verify no JavaScript errors
    expect(errors).toEqual([]);
  });

  test('check what buttons appear after email entry', async ({ page }) => {
    await page.goto(frontendUrl);
    await page.waitForSelector('.card', { timeout: 5000 });

    // Enter email
    await page.locator('input[type="email"]').first().fill('eliyahu@eliyahu.ai');
    await page.waitForTimeout(500);

    // Click first button
    await page.locator('.card button').first().click();
    await page.waitForTimeout(3000);

    // Get all cards and their content
    const cards = await page.locator('.card').all();
    console.log(`\n=== Found ${cards.length} card(s) ===`);

    for (let i = 0; i < cards.length; i++) {
      const cardText = await cards[i].textContent();
      const cardTitle = await cards[i].locator('.card-title').textContent().catch(() => 'No title');
      console.log(`\nCard ${i + 1}:`);
      console.log(`Title: ${cardTitle}`);
      console.log(`Full text: ${cardText?.substring(0, 200)}...`);

      // List buttons in this card
      const cardButtons = await cards[i].locator('button').all();
      console.log(`Buttons in this card: ${cardButtons.length}`);
      for (let j = 0; j < cardButtons.length; j++) {
        const btnText = await cardButtons[j].textContent();
        console.log(`  Button ${j + 1}: "${btnText}"`);
      }
    }
  });

});
