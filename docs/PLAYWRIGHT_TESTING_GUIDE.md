# Playwright Testing Guide

## Overview

This project uses [Playwright](https://playwright.dev/) for automated end-to-end testing of the Hyperplexity frontend. Playwright is a powerful browser automation framework that allows us to test the complete user experience across different browsers.

## Why Playwright?

- **Multi-browser support**: Test on Chromium, Firefox, and WebKit
- **Fast and reliable**: Built for modern web apps with auto-waiting
- **Developer experience**: Excellent debugging tools and test generation
- **CI/CD ready**: Easy integration with continuous integration pipelines
- **File protocol support**: Can test local HTML files without a server

## Installation

### Prerequisites

- Node.js (v16 or higher recommended)
- npm or yarn package manager

### Setup Steps

1. **Install Playwright** (already done in this project):
   ```bash
   npm init -y  # Creates package.json if needed
   npm install --save-dev @playwright/test
   ```

2. **Install browsers** (Chromium, Firefox, WebKit):
   ```bash
   npx playwright install
   ```

3. **Install system dependencies** (Linux/WSL only):
   ```bash
   # If you get browser dependency errors, run:
   sudo apt-get update
   sudo apt-get install -y \
       libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
       libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
       libxdamage1 libxfixes3 libxrandr2 libgbm1 \
       libasound2 libpango-1.0-0 libcairo2
   ```

## Project Structure

```
perplexityValidator/
├── tests/
│   ├── frontend.spec.js      # Basic frontend integration tests
│   ├── user-flow.spec.js      # Complete user journey tests
│   └── example.spec.js        # Playwright example (can delete)
├── playwright.config.js       # Playwright configuration
└── package.json              # Node dependencies
```

## Configuration

### playwright.config.js

```javascript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  expect: {
    timeout: 5000
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
});
```

### package.json

```json
{
  "type": "module",
  "scripts": {
    "test": "playwright test",
    "test:frontend": "playwright test frontend.spec.js",
    "test:user-flow": "playwright test user-flow.spec.js",
    "test:debug": "playwright test --debug",
    "test:headed": "playwright test --headed",
    "test:ui": "playwright test --ui"
  },
  "devDependencies": {
    "@playwright/test": "^1.48.2"
  }
}
```

## Writing Tests

### Basic Test Structure

```javascript
// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {

  test('should do something', async ({ page }) => {
    // 1. Navigate to page
    await page.goto('https://example.com');

    // 2. Interact with elements
    await page.click('button#submit');

    // 3. Assert expected outcome
    await expect(page.locator('.result')).toBeVisible();
  });

});
```

### Testing Local HTML Files

```javascript
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend.html');
const frontendUrl = `file://${frontendPath}`;

test('loads local file', async ({ page }) => {
  await page.goto(frontendUrl);
  await page.waitForSelector('.card', { timeout: 5000 });
});
```

### Common Patterns

#### 1. Finding Elements

```javascript
// By ID
const element = page.locator('#element-id');

// By class
const cards = page.locator('.card');

// By CSS selector
const button = page.locator('button.primary');

// By text content
const loginButton = page.locator('button', { hasText: 'Login' });

// By attribute
const emailInput = page.locator('input[type="email"]');

// First/Last/Nth element
const firstCard = page.locator('.card').first();
const lastCard = page.locator('.card').last();
const thirdCard = page.locator('.card').nth(2);

// Get all matching elements
const allButtons = await page.locator('button').all();
```

#### 2. Interacting with Elements

```javascript
// Click
await page.click('button#submit');
await page.locator('button').click();

// Fill input
await page.fill('input[type="email"]', 'test@example.com');
await page.locator('input[type="email"]').fill('test@example.com');

// Type (with realistic timing)
await page.type('input', 'Hello World');

// Select dropdown
await page.selectOption('select', 'option-value');

// Check/uncheck checkbox
await page.check('input[type="checkbox"]');
await page.uncheck('input[type="checkbox"]');

// Upload file
await page.setInputFiles('input[type="file"]', '/path/to/file.pdf');
```

#### 3. Waiting Strategies

```javascript
// Wait for element to be visible
await page.waitForSelector('.card', { timeout: 5000 });

// Wait for navigation
await page.waitForURL('**/dashboard');

// Wait for specific timeout
await page.waitForTimeout(2000);

// Wait for network idle
await page.waitForLoadState('networkidle');

// Wait for element state
await page.locator('button').waitFor({ state: 'visible' });
await page.locator('button').waitFor({ state: 'hidden' });
```

#### 4. Assertions

```javascript
// Element visibility
await expect(page.locator('.card')).toBeVisible();
await expect(page.locator('.error')).toBeHidden();

// Text content
await expect(page.locator('.title')).toHaveText('Welcome');
await expect(page.locator('.title')).toContainText('Welcome');

// Element count
await expect(page.locator('.card')).toHaveCount(3);

// Input value
await expect(page.locator('input')).toHaveValue('test@example.com');

// Attribute
await expect(page.locator('button')).toHaveAttribute('disabled');

// Page title
await expect(page).toHaveTitle(/Hyperplexity/);

// URL
await expect(page).toHaveURL('https://example.com/dashboard');

// JavaScript expression
const isValid = await page.evaluate(() => {
  return document.querySelector('.form').checkValidity();
});
expect(isValid).toBe(true);
```

#### 5. Console and Error Handling

```javascript
test('captures console messages', async ({ page }) => {
  const consoleLogs = [];
  const errors = [];

  // Capture console logs
  page.on('console', msg => {
    consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
  });

  // Capture JavaScript errors
  page.on('pageerror', error => {
    errors.push(error.message);
  });

  await page.goto(frontendUrl);

  // Verify no errors
  expect(errors).toEqual([]);

  // Log console messages for debugging
  if (errors.length > 0) {
    console.log('Errors:', errors);
  }
});
```

#### 6. Multiple Cards/Elements

```javascript
test('lists all buttons in each card', async ({ page }) => {
  await page.goto(frontendUrl);

  // Get all cards
  const cards = await page.locator('.card').all();
  console.log(`Found ${cards.length} cards`);

  // Iterate through each card
  for (let i = 0; i < cards.length; i++) {
    const cardTitle = await cards[i].locator('.card-title').textContent();
    console.log(`\nCard ${i + 1}: ${cardTitle}`);

    // List buttons in this card
    const buttons = await cards[i].locator('button').all();
    for (let j = 0; j < buttons.length; j++) {
      const btnText = await buttons[j].textContent();
      console.log(`  Button ${j + 1}: "${btnText}"`);
    }
  }
});
```

## Running Tests

### Command Line Options

```bash
# Run all tests
npx playwright test

# Run specific test file
npx playwright test frontend.spec.js

# Run specific browser
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit

# Run in headed mode (see browser)
npx playwright test --headed

# Run in debug mode
npx playwright test --debug

# Run UI mode (interactive)
npx playwright test --ui

# Run with specific timeout
npx playwright test --timeout=60000

# Run tests matching pattern
npx playwright test --grep "email"

# Run with verbose output
npx playwright test --reporter=list

# Generate HTML report
npx playwright show-report
```

### NPM Scripts

```bash
# Run all tests
npm test

# Run frontend tests only
npm run test:frontend

# Run user flow tests only
npm run test:user-flow

# Run in debug mode
npm run test:debug

# Run with visible browser
npm run test:headed

# Run interactive UI
npm run test:ui
```

## Real-World Examples from This Project

### Example 1: Basic Frontend Integration Test

```javascript
// tests/frontend.spec.js
test('email card appears on page load', async ({ page }) => {
  await page.goto(frontendUrl);

  // Wait for the card container
  await page.waitForSelector('#cardContainer', { timeout: 5000 });

  // Wait for a card to be created
  await page.waitForSelector('.card', { timeout: 3000 });

  // Verify the card exists
  const card = await page.$('.card');
  expect(card).not.toBeNull();
});
```

### Example 2: Testing Email Input

```javascript
test('can enter email address', async ({ page }) => {
  await page.goto(frontendUrl);

  // Wait for input to appear
  await page.waitForSelector('input[type="email"]', { timeout: 3000 });

  // Enter email
  await page.fill('input[type="email"]', 'test@example.com');

  // Verify email was entered
  const value = await page.inputValue('input[type="email"]');
  expect(value).toBe('test@example.com');
});
```

### Example 3: Complete User Flow Test

```javascript
// tests/user-flow.spec.js
test('complete flow from email entry to demo selection', async ({ page }) => {
  test.setTimeout(30000);

  // Step 1: Load page
  await page.goto(frontendUrl);
  await page.waitForSelector('.card', { timeout: 5000 });

  // Step 2: Enter email
  const emailInput = page.locator('input[type="email"]').first();
  await emailInput.fill('eliyahu@eliyahu.ai');

  // Step 3: Click validate button
  const firstButton = page.locator('.card button').first();
  await firstButton.click();

  // Step 4: Wait for Get Started card
  await page.waitForTimeout(2000);

  // Step 5: Click "Explore a demo table"
  const exploreButton = page.locator('button').filter({
    hasText: /demo/i
  }).first();
  await exploreButton.click();

  // Step 6: Verify demo selection card appears
  await page.waitForTimeout(2000);
  const hasDemoOptions = await page.evaluate(() => {
    const text = document.body.textContent || '';
    return text.includes('Select') ||
           text.includes('Demo') ||
           text.includes('Biden');
  });

  expect(hasDemoOptions).toBe(true);
});
```

### Example 4: No JavaScript Errors Test

```javascript
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
  await page.waitForTimeout(1000);

  // Check for no errors
  expect(errors).toEqual([]);
});
```

## Debugging Tests

### 1. Visual Debugging

```bash
# Run with visible browser
npx playwright test --headed

# Run in debug mode (step through)
npx playwright test --debug

# Run specific test in debug mode
npx playwright test frontend.spec.js:39 --debug
```

### 2. Screenshots and Videos

```javascript
// Take screenshot
await page.screenshot({ path: 'screenshot.png' });

// Take screenshot of specific element
await page.locator('.card').screenshot({ path: 'card.png' });

// Configure video recording in playwright.config.js
use: {
  video: 'on-first-retry',
  screenshot: 'only-on-failure',
}
```

### 3. Console Logging

```javascript
test('debug card creation', async ({ page }) => {
  // Log all console messages
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));

  await page.goto(frontendUrl);

  // Get all card IDs
  const cardIds = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('.card'))
      .map(card => card.id);
  });
  console.log('Card IDs:', cardIds);

  // Get page HTML for inspection
  const html = await page.content();
  console.log('Page HTML length:', html.length);
});
```

### 4. Playwright Inspector

```bash
# Open Playwright Inspector
npx playwright test --debug

# Commands in Inspector:
# - Step over (execute next action)
# - Step into (go into function)
# - Resume (run until next breakpoint)
# - Pick locator (click element to get selector)
```

### 5. Trace Viewer

```javascript
// Configure in playwright.config.js
use: {
  trace: 'on-first-retry',
}

// View trace after test
// npx playwright show-trace trace.zip
```

## Best Practices

### 1. Use Descriptive Test Names

```javascript
// Good
test('should display error message when email is invalid', async ({ page }) => {});

// Bad
test('test1', async ({ page }) => {});
```

### 2. Use Page Object Model for Complex Tests

```javascript
// pages/EmailPage.js
export class EmailPage {
  constructor(page) {
    this.page = page;
    this.emailInput = page.locator('input[type="email"]');
    this.submitButton = page.locator('button[type="submit"]');
  }

  async goto() {
    await this.page.goto('file:///path/to/frontend.html');
  }

  async enterEmail(email) {
    await this.emailInput.fill(email);
  }

  async submit() {
    await this.submitButton.click();
  }
}

// tests/email.spec.js
import { EmailPage } from '../pages/EmailPage';

test('submit email', async ({ page }) => {
  const emailPage = new EmailPage(page);
  await emailPage.goto();
  await emailPage.enterEmail('test@example.com');
  await emailPage.submit();
});
```

### 3. Use Fixtures for Common Setup

```javascript
// tests/fixtures.js
import { test as base } from '@playwright/test';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export const test = base.extend({
  frontendPage: async ({ page }, use) => {
    const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend.html');
    await page.goto(`file://${frontendPath}`);
    await page.waitForSelector('#cardContainer');
    await use(page);
  },
});

export { expect } from '@playwright/test';

// Usage
import { test, expect } from './fixtures';

test('test with frontend loaded', async ({ frontendPage }) => {
  await expect(frontendPage.locator('.card')).toBeVisible();
});
```

### 4. Keep Tests Independent

```javascript
// Bad - tests depend on each other
test('create user', async ({ page }) => {
  // Creates user
});

test('delete user', async ({ page }) => {
  // Assumes user exists from previous test
});

// Good - each test is independent
test('create and delete user', async ({ page }) => {
  // Create user
  // Delete user
});
```

### 5. Use Auto-Waiting

```javascript
// Bad - unnecessary explicit waits
await page.waitForTimeout(1000);
await page.click('button');

// Good - Playwright waits automatically
await page.click('button');
```

## Advanced Patterns

### Testing API Calls

```javascript
test('intercepts API calls', async ({ page }) => {
  // Mock API response
  await page.route('**/api/validate', route => {
    route.fulfill({
      status: 200,
      body: JSON.stringify({ success: true, data: 'mocked' })
    });
  });

  await page.goto(frontendUrl);

  // Wait for API call
  const response = await page.waitForResponse('**/api/validate');
  expect(response.status()).toBe(200);
});
```

### Testing File Downloads

```javascript
test('downloads config file', async ({ page }) => {
  await page.goto(frontendUrl);

  // Start waiting for download
  const downloadPromise = page.waitForEvent('download');

  // Click download button
  await page.click('#download-config');

  // Wait for download
  const download = await downloadPromise;

  // Save to specific path
  await download.saveAs('/tmp/config.json');

  // Verify filename
  expect(download.suggestedFilename()).toBe('config.json');
});
```

### Testing Drag and Drop

```javascript
test('uploads file via drag and drop', async ({ page }) => {
  await page.goto(frontendUrl);

  // Create file buffer
  const buffer = Buffer.from('test content');

  // Simulate file drop
  await page.locator('.drop-zone').setInputFiles({
    name: 'test.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: buffer
  });

  await expect(page.locator('.file-info')).toBeVisible();
});
```

### Testing WebSocket Connections

```javascript
test('establishes WebSocket connection', async ({ page }) => {
  const wsMessages = [];

  // Listen for WebSocket frames
  page.on('websocket', ws => {
    ws.on('framereceived', event => {
      wsMessages.push(event.payload);
    });
  });

  await page.goto(frontendUrl);
  await page.click('#start-validation');

  // Wait for WebSocket messages
  await page.waitForTimeout(2000);
  expect(wsMessages.length).toBeGreaterThan(0);
});
```

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Playwright Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    timeout-minutes: 60
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - uses: actions/setup-node@v3
      with:
        node-version: 18

    - name: Install dependencies
      run: npm ci

    - name: Install Playwright Browsers
      run: npx playwright install --with-deps

    - name: Run Playwright tests
      run: npx playwright test

    - uses: actions/upload-artifact@v3
      if: always()
      with:
        name: playwright-report
        path: playwright-report/
        retention-days: 30
```

## Common Issues and Solutions

### Issue: Browser Not Found

```bash
# Solution: Install browsers
npx playwright install
```

### Issue: System Dependencies Missing (Linux/WSL)

```bash
# Solution: Install system dependencies
npx playwright install-deps
# Or manually:
sudo apt-get install -y libnss3 libnspr4 libatk1.0-0
```

### Issue: Timeout Waiting for Element

```javascript
// Solution: Increase timeout or check selector
await page.waitForSelector('.card', { timeout: 10000 });

// Or use better waiting strategy
await page.locator('.card').waitFor({ state: 'visible' });
```

### Issue: Element Not Clickable

```javascript
// Solution: Wait for element to be ready
await page.locator('button').waitFor({ state: 'visible' });
await page.locator('button').click();

// Or force click
await page.locator('button').click({ force: true });
```

### Issue: Test Flakiness

```javascript
// Solution: Use auto-retry assertions
await expect(page.locator('.result')).toBeVisible();

// Add retry in config
retries: 2,

// Use better waiting
await page.waitForLoadState('networkidle');
```

## Future Testing Ideas

### 1. Visual Regression Testing

```javascript
// Take baseline screenshot
await page.screenshot({ path: 'baseline.png' });

// Compare against baseline in future tests
const screenshot = await page.screenshot();
expect(screenshot).toMatchSnapshot('homepage.png');
```

### 2. Performance Testing

```javascript
test('page loads within acceptable time', async ({ page }) => {
  const start = Date.now();
  await page.goto(frontendUrl);
  await page.waitForLoadState('networkidle');
  const loadTime = Date.now() - start;

  expect(loadTime).toBeLessThan(3000); // 3 seconds
});
```

### 3. Accessibility Testing

```javascript
import { injectAxe, checkA11y } from 'axe-playwright';

test('page is accessible', async ({ page }) => {
  await page.goto(frontendUrl);
  await injectAxe(page);
  await checkA11y(page);
});
```

### 4. Cross-Browser Testing

```javascript
// Already configured with chromium, firefox, webkit
// Run all browsers:
npx playwright test

// Compare results across browsers
```

### 5. Mobile Testing

```javascript
// Add to playwright.config.js
{
  name: 'Mobile Chrome',
  use: { ...devices['Pixel 5'] },
},
{
  name: 'Mobile Safari',
  use: { ...devices['iPhone 12'] },
}
```

## Resources

- **Official Docs**: https://playwright.dev/
- **API Reference**: https://playwright.dev/docs/api/class-playwright
- **Best Practices**: https://playwright.dev/docs/best-practices
- **VS Code Extension**: Playwright Test for VSCode
- **Discord Community**: https://aka.ms/playwright/discord

## Quick Reference Card

```bash
# Installation
npm install --save-dev @playwright/test
npx playwright install

# Run tests
npx playwright test                    # All tests
npx playwright test file.spec.js       # Single file
npx playwright test --project=chromium # Single browser
npx playwright test --headed           # Visible browser
npx playwright test --debug            # Debug mode
npx playwright test --ui               # Interactive UI

# Generate tests
npx playwright codegen https://example.com

# View reports
npx playwright show-report

# Update snapshots
npx playwright test --update-snapshots
```

## Test Checklist

When writing new tests, ensure:

- [ ] Test has descriptive name
- [ ] Test is independent (doesn't rely on other tests)
- [ ] Uses appropriate waiting strategies (not arbitrary timeouts)
- [ ] Has clear assertions
- [ ] Handles errors appropriately
- [ ] Cleans up after itself
- [ ] Has comments for complex logic
- [ ] Runs reliably (no flakiness)
- [ ] Uses meaningful variable names
- [ ] Logs helpful debugging information

---

**Last Updated**: 2026-01-10
**Playwright Version**: 1.48.2
**Project**: Hyperplexity Validator
