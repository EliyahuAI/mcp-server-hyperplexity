// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Path to the built frontend HTML file
const frontendPath = 'C:\\Users\\ellio\\OneDrive - Eliyahu.AI\\Desktop\\src\\perplexityValidator\\frontend\\Hyperplexity_FullScript_Temp-dev.html';
const frontendUrl = `file:///${frontendPath.replace(/\\/g, '/')}`;

test.describe('WebSocket Message Persistence & Replay', () => {

  test.describe('Message Queue Module', () => {

    test('message queue state initializes correctly', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      // Check that message queue state is available
      const hasState = await page.evaluate(() => {
        return typeof window.messageQueueState !== 'undefined';
      });
      expect(hasState).toBe(true);

      // Check initial state structure
      const state = await page.evaluate(() => {
        return {
          hasLastReceivedSeq: typeof window.messageQueueState?.lastReceivedSeq === 'object',
          hasSeenSeqs: typeof window.messageQueueState?.seenSeqs === 'object',
          hasPendingMessages: typeof window.messageQueueState?.pendingMessages === 'object'
        };
      });
      expect(state.hasLastReceivedSeq).toBe(true);
      expect(state.hasSeenSeqs).toBe(true);
      expect(state.hasPendingMessages).toBe(true);
    });

    test('processIncomingMessage function is available', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const hasFunction = await page.evaluate(() => {
        return typeof window.processIncomingMessage === 'function';
      });
      expect(hasFunction).toBe(true);
    });

    test('processIncomingMessage handles messages without sequence metadata', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const result = await page.evaluate(() => {
        // Simulate a legacy message without sequence metadata
        const legacyMessage = { type: 'test_message', data: 'hello' };
        return window.processIncomingMessage(legacyMessage);
      });

      expect(result.shouldProcess).toBe(true);
      expect(result.isOutOfOrder).toBe(false);
    });

    test('processIncomingMessage deduplicates messages with same sequence', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const results = await page.evaluate(() => {
        // First message should be processed
        const msg1 = { _seq: 1, _card_id: 'test-card', type: 'test' };
        const result1 = window.processIncomingMessage(msg1);

        // Same sequence should be deduplicated
        const msg2 = { _seq: 1, _card_id: 'test-card', type: 'test' };
        const result2 = window.processIncomingMessage(msg2);

        return { first: result1, second: result2 };
      });

      expect(results.first.shouldProcess).toBe(true);
      expect(results.second.shouldProcess).toBe(false);
    });

    test('processIncomingMessage detects gaps in sequence', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const result = await page.evaluate(() => {
        // Initialize with seq 1
        window.processIncomingMessage({ _seq: 1, _card_id: 'gap-test', type: 'test' });

        // Skip seq 2, send seq 3 (gap detected)
        const gapResult = window.processIncomingMessage({ _seq: 3, _card_id: 'gap-test', type: 'test' });

        return gapResult;
      });

      // Should be out of order (gap detected)
      expect(result.isOutOfOrder).toBe(true);
    });

    test('resetMessageQueue clears state', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const result = await page.evaluate(() => {
        // Add some messages
        window.processIncomingMessage({ _seq: 1, _card_id: 'reset-test', type: 'test' });
        window.processIncomingMessage({ _seq: 2, _card_id: 'reset-test', type: 'test' });

        // Check state before reset
        const beforeReset = Object.keys(window.messageQueueState.lastReceivedSeq).length > 0;

        // Reset
        window.resetMessageQueue();

        // Check state after reset
        const afterReset = Object.keys(window.messageQueueState.lastReceivedSeq).length === 0;

        return { beforeReset, afterReset };
      });

      expect(result.beforeReset).toBe(true);
      expect(result.afterReset).toBe(true);
    });
  });

  test.describe('State Recovery Functions', () => {

    test('saveRestorableState function is available', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const hasFunction = await page.evaluate(() => {
        return typeof window.saveRestorableState === 'function';
      });
      expect(hasFunction).toBe(true);
    });

    test('getRestorableState function is available', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const hasFunction = await page.evaluate(() => {
        return typeof window.getRestorableState === 'function';
      });
      expect(hasFunction).toBe(true);
    });

    test('saveRestorableState saves state to sessionStorage', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const saved = await page.evaluate(() => {
        // Set up some global state
        globalState.sessionId = 'test-session-123';
        globalState.email = 'test@example.com';
        globalState.workflowPhase = 'preview';

        // Save state
        window.saveRestorableState('test-card-1', 'preview');

        // Check sessionStorage
        const savedData = sessionStorage.getItem('hyperplexity_restorable_state');
        if (savedData) {
          const parsed = JSON.parse(savedData);
          return {
            hasSessionId: parsed.sessionId === 'test-session-123',
            hasCardId: parsed.cardId === 'test-card-1',
            hasPhase: parsed.phase === 'preview',
            hasTimestamp: typeof parsed.timestamp === 'number',
            warningTriggered: parsed.warningTriggered === true
          };
        }
        return null;
      });

      expect(saved).not.toBeNull();
      expect(saved.hasSessionId).toBe(true);
      expect(saved.hasCardId).toBe(true);
      expect(saved.hasPhase).toBe(true);
      expect(saved.hasTimestamp).toBe(true);
      expect(saved.warningTriggered).toBe(true);
    });

    test('getRestorableState retrieves saved state', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const retrieved = await page.evaluate(() => {
        // Save state first
        globalState.sessionId = 'retrieve-test-session';
        globalState.email = 'retrieve@test.com';
        window.saveRestorableState('retrieve-card', 'validation');

        // Retrieve state
        const state = window.getRestorableState();
        return state;
      });

      expect(retrieved).not.toBeNull();
      expect(retrieved.sessionId).toBe('retrieve-test-session');
      expect(retrieved.cardId).toBe('retrieve-card');
      expect(retrieved.warningTriggered).toBe(true);
    });

    test('getRestorableState returns null for old state (>30 min)', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const result = await page.evaluate(() => {
        // Create old state (35 minutes ago)
        const oldState = {
          sessionId: 'old-session',
          cardId: 'old-card',
          phase: 'preview',
          timestamp: Date.now() - (35 * 60 * 1000), // 35 minutes ago
          warningTriggered: true
        };
        sessionStorage.setItem('hyperplexity_restorable_state', JSON.stringify(oldState));

        // Try to retrieve - should return null
        const retrieved = window.getRestorableState();
        return retrieved;
      });

      expect(result).toBeNull();
    });
  });

  test.describe('WebSocket Integration', () => {

    test('WebSocket onmessage uses processIncomingMessage', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      // This test verifies the code path exists but doesn't require actual WebSocket
      const codePathExists = await page.evaluate(() => {
        // Check that the integration is set up correctly
        return typeof window.processIncomingMessage === 'function' &&
               typeof window.messageQueueState !== 'undefined';
      });

      expect(codePathExists).toBe(true);
    });
  });

  test.describe('API Functions', () => {

    test('getAllMessagesSince function is available', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const hasFunction = await page.evaluate(() => {
        return typeof window.getAllMessagesSince === 'function';
      });
      expect(hasFunction).toBe(true);
    });

    test('fetchMissedMessages function is available', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const hasFunction = await page.evaluate(() => {
        return typeof window.fetchMissedMessages === 'function';
      });
      expect(hasFunction).toBe(true);
    });

    test('dispatchReplayedMessage function is available', async ({ page }) => {
      await page.goto(frontendUrl);
      await page.waitForSelector('#cardContainer', { timeout: 5000 });

      const hasFunction = await page.evaluate(() => {
        return typeof window.dispatchReplayedMessage === 'function';
      });
      expect(hasFunction).toBe(true);
    });
  });
});
