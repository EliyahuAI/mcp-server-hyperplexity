/* ========================================
 * 03b-message-queue.js - Message Queue & Deduplication
 *
 * Manages WebSocket message ordering, deduplication, and replay
 * for state recovery after page refresh or connection interruption.
 *
 * Dependencies: 00-config.js
 * Loaded before: 03-websocket.js (provides processIncomingMessage)
 * ======================================== */

// Message queue state
const messageQueueState = {
    // Track last received sequence per card_id: { 'card-4': 10, 'validation': 5 }
    lastReceivedSeq: {},
    // Track all seen sequences for deduplication: { 'card-4': Set([1, 2, 3]) }
    seenSeqs: {},
    // Pending messages waiting for gaps to be filled: { 'card-4': [{ seq: 3, data: {...} }] }
    pendingMessages: {},
    // Whether we're currently fetching missed messages
    isFetching: false,
    // Maximum gap before triggering fetch (prevents fetching on initial messages)
    maxGapBeforeFetch: 5
};

/**
 * Process an incoming WebSocket message with sequence tracking.
 * Returns { shouldProcess: boolean, isOutOfOrder: boolean }
 */
function processIncomingMessage(data) {
    // Ensure sequence is an integer (may come as string from JSON/DynamoDB)
    const seq = data._seq !== undefined ? parseInt(data._seq, 10) : undefined;
    const cardId = data._card_id;

    // If no sequence metadata, process normally (legacy message)
    if (seq === undefined || isNaN(seq) || !cardId) {
        return { shouldProcess: true, isOutOfOrder: false };
    }

    // Initialize tracking for this card_id
    if (messageQueueState.seenSeqs[cardId] === undefined) {
        messageQueueState.seenSeqs[cardId] = new Set();
    }
    if (messageQueueState.lastReceivedSeq[cardId] === undefined) {
        messageQueueState.lastReceivedSeq[cardId] = 0;
    }

    // Check for duplicate
    if (messageQueueState.seenSeqs[cardId].has(seq)) {
        return { shouldProcess: false, isOutOfOrder: false };
    }

    // Mark as seen
    messageQueueState.seenSeqs[cardId].add(seq);

    const expectedSeq = messageQueueState.lastReceivedSeq[cardId] + 1;

    // Check for gap (missed messages)
    if (seq > expectedSeq) {
        const gap = seq - expectedSeq;

        // Only fetch if gap is reasonable
        if (gap <= messageQueueState.maxGapBeforeFetch) {
            // Queue this message and fetch missed ones
            if (!messageQueueState.pendingMessages[cardId]) {
                messageQueueState.pendingMessages[cardId] = [];
            }
            messageQueueState.pendingMessages[cardId].push({ seq, data });

            // Trigger fetch for missed messages
            fetchMissedMessages(cardId, messageQueueState.lastReceivedSeq[cardId], seq - 1);

            return { shouldProcess: false, isOutOfOrder: true };
        }

        // Gap too large - just reset and process this message
        messageQueueState.lastReceivedSeq[cardId] = seq;
        return { shouldProcess: true, isOutOfOrder: false };
    }

    // Normal case - in order
    messageQueueState.lastReceivedSeq[cardId] = seq;
    return { shouldProcess: true, isOutOfOrder: false };
}

/**
 * Fetch missed messages from the backend replay API.
 */
async function fetchMissedMessages(cardId, sinceSeq, toSeq) {
    if (messageQueueState.isFetching) {
        return;
    }

    if (!globalState.sessionId) {
        return;
    }

    messageQueueState.isFetching = true;

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'getMessagesForCard',
                session_id: globalState.sessionId,
                card_id: cardId,
                since_seq: sinceSeq,
                limit: 50
            })
        });

        const data = await response.json();

        if (data.success && data.messages && data.messages.length > 0) {

            // Process each missed message
            for (const msg of data.messages) {
                const msgData = msg.message_data || msg;
                // Ensure sequence is integer
                const msgSeq = parseInt(msg.message_seq || msgData._seq, 10);

                if (isNaN(msgSeq)) continue;

                // Mark as seen
                if (!messageQueueState.seenSeqs[cardId]) {
                    messageQueueState.seenSeqs[cardId] = new Set();
                }
                if (!messageQueueState.seenSeqs[cardId].has(msgSeq)) {
                    messageQueueState.seenSeqs[cardId].add(msgSeq);

                    // Dispatch to appropriate handler
                    dispatchReplayedMessage(msgData);
                }
            }

            // Update last received seq (ensure integer)
            messageQueueState.lastReceivedSeq[cardId] = parseInt(data.last_seq, 10) || 0;

            // Process any pending messages now that gaps are filled
            processPendingMessages(cardId);
        }
    } catch (error) {
        console.error('[MESSAGE_QUEUE] Error fetching missed messages:', error);
    } finally {
        messageQueueState.isFetching = false;
    }
}

/**
 * Process pending messages after gaps have been filled.
 */
function processPendingMessages(cardId) {
    const pending = messageQueueState.pendingMessages[cardId];
    if (!pending || pending.length === 0) return;

    // Sort by sequence
    pending.sort((a, b) => a.seq - b.seq);

    // Process messages in order
    const stillPending = [];
    for (const item of pending) {
        const expectedSeq = messageQueueState.lastReceivedSeq[cardId] + 1;

        if (item.seq === expectedSeq) {
            messageQueueState.lastReceivedSeq[cardId] = item.seq;
            dispatchReplayedMessage(item.data);
        } else if (item.seq > expectedSeq) {
            stillPending.push(item);
        }
        // If seq < expectedSeq, it's a duplicate - skip
    }

    messageQueueState.pendingMessages[cardId] = stillPending;
}

/**
 * Dispatch a replayed message to the appropriate handler.
 * This re-routes messages that were fetched from the replay API.
 */
function dispatchReplayedMessage(data) {

    // Dispatch based on message type
    const messageType = data.type || data.message_type;

    // Route to card handlers if registered
    if (typeof cardHandlers !== 'undefined' && cardHandlers.size > 0) {
        cardHandlers.forEach((handlerInfo, cardId) => {
            if (handlerInfo.messageTypes.includes(messageType)) {
                try {
                    handlerInfo.callback(data, cardId);
                } catch (e) {
                    console.error(`[MESSAGE_QUEUE] Error in replayed message handler for ${cardId}:`, e);
                }
            }
        });
    }

    // Route through the standard message router (defined in 03-websocket.js)
    if (typeof routeMessage === 'function') {
        try {
            const sessionId = globalState?.sessionId || data.session_id;
            routeMessage(data, sessionId);
        } catch (e) {
            console.error('[MESSAGE_QUEUE] Error routing replayed message:', e);
        }
    }
}

/**
 * Get all messages since a sequence number for a session (for state recovery).
 * Returns a promise that resolves with the messages.
 */
async function getAllMessagesSince(sessionId, sinceSeq = 0) {
    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'getMessagesSince',
                session_id: sessionId,
                since_seq: sinceSeq,
                limit: 100
            })
        });

        const data = await response.json();

        if (data.success) {
            return {
                messages: data.messages || [],
                lastSeq: data.last_seq || sinceSeq,
                hasMore: data.has_more || false
            };
        }

        return { messages: [], lastSeq: sinceSeq, hasMore: false };
    } catch (error) {
        console.error('[MESSAGE_QUEUE] Error fetching all messages:', error);
        return { messages: [], lastSeq: sinceSeq, hasMore: false };
    }
}

/**
 * Reset message queue state for a specific card or all cards.
 */
function resetMessageQueue(cardId = null) {
    if (cardId) {
        delete messageQueueState.lastReceivedSeq[cardId];
        delete messageQueueState.seenSeqs[cardId];
        delete messageQueueState.pendingMessages[cardId];
    } else {
        messageQueueState.lastReceivedSeq = {};
        messageQueueState.seenSeqs = {};
        messageQueueState.pendingMessages = {};
    }
}

/**
 * Save current message queue state to localStorage for recovery.
 */
function saveMessageQueueState() {
    try {
        const stateToSave = {
            lastReceivedSeq: messageQueueState.lastReceivedSeq,
            timestamp: Date.now()
        };
        localStorage.setItem('messageQueueState', JSON.stringify(stateToSave));
    } catch (e) {
        console.error('[MESSAGE_QUEUE] Error saving state:', e);
    }
}

/**
 * Restore message queue state from localStorage.
 */
function restoreMessageQueueState() {
    try {
        const saved = localStorage.getItem('messageQueueState');
        if (saved) {
            const state = JSON.parse(saved);
            // Only restore if less than 5 minutes old
            if (state.timestamp && (Date.now() - state.timestamp) < 5 * 60 * 1000) {
                messageQueueState.lastReceivedSeq = state.lastReceivedSeq || {};
                return true;
            }
        }
    } catch (e) {
        console.error('[MESSAGE_QUEUE] Error restoring state:', e);
    }
    return false;
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.messageQueueState = messageQueueState;
    window.processIncomingMessage = processIncomingMessage;
    window.fetchMissedMessages = fetchMissedMessages;
    window.getAllMessagesSince = getAllMessagesSince;
    window.resetMessageQueue = resetMessageQueue;
    window.saveMessageQueueState = saveMessageQueueState;
    window.restoreMessageQueueState = restoreMessageQueueState;
    window.dispatchReplayedMessage = dispatchReplayedMessage;
}
