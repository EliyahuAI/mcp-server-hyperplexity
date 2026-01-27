/* ========================================
 * Cards Module
 * Card creation, thinking indicators, progress tracking, and button management
 *
 * Dependencies: 00-config.js (globalState)
 *               01-utils.js (generateCardId, getConfidenceColor, showMessage)
 * ======================================== */

            // ============================================
            // GLOBAL PROGRESS SYSTEM REMOVED
            // ============================================
            // All progress now handled at card level via showThinkingInCard()
            
            // Stub object to prevent errors - all calls are no-ops
            const globalProgress = {
                show: () => {},
                update: () => {},
                complete: () => {},
                hide: () => {},
                showIdle: () => {},
                test: () => {}
            };

            function createThinkingIndicator(cardId, message = 'Processing...', withProgress = false) {
                const indicator = document.createElement('div');
                indicator.className = withProgress ? 'thinking-indicator with-progress' : 'thinking-indicator';
                indicator.id = `${cardId}-thinking`;

                if (withProgress) {
                    indicator.innerHTML = `
                        <div class="thinking-text">${message}</div>
                        <div class="progress-track">
                            <div class="progress-square-wrapper">
                                <div class="progress-square"></div>
                            </div>
                        </div>
                        <div class="progress-text">${message}</div>
                        <div class="ticker-row" id="${cardId}-ticker" style="display: none;">
                            <div class="ticker-content" id="${cardId}-ticker-content"></div>
                        </div>
                    `;
                } else {
                    indicator.innerHTML = `
                        <div class="thinking-square-wrapper">
                            <div class="thinking-square"></div>
                        </div>
                        <div class="thinking-text">${message}</div>
                        <div class="ticker-row" id="${cardId}-ticker" style="display: none;">
                            <div class="ticker-content" id="${cardId}-ticker-content"></div>
                        </div>
                    `;
                }
                return indicator;
            }

            function showThinkingInCard(cardId, message = 'Processing...', withProgress = false) {
                const card = document.getElementById(cardId);
                if (!card) return;

                // Check if an indicator already exists
                const existing = document.getElementById(`${cardId}-thinking`);

                // CRITICAL FIX: If indicator exists with progress, preserve it and just update the message
                // This prevents the progress from resetting to 0 when the indicator is recreated
                if (existing && existing.classList.contains('with-progress') && withProgress) {
                    // Update the message text only, preserve progress state
                    const progressText = existing.querySelector('.progress-text');
                    if (progressText) {
                        progressText.textContent = message;
                    }
                    return existing;
                }

                // Remove existing indicator only if we need to create a new type
                if (existing) existing.remove();

                // Add new thinking indicator
                const indicator = createThinkingIndicator(cardId, message, withProgress);
                card.appendChild(indicator);

                // Reset any error state on the square and wrapper
                const square = indicator.querySelector('.thinking-square, .progress-square');
                const wrapper = indicator.querySelector('.progress-square-wrapper, .thinking-square-wrapper');
                if (square) {
                    square.classList.remove('error');
                }
                if (wrapper) {
                    wrapper.classList.remove('error');
                }

                // Trigger progress bar grow animation if this has progress
                if (withProgress) {
                    const track = indicator.querySelector('.progress-track');
                    const progressWrapper = indicator.querySelector('.progress-square-wrapper');
                    if (track) track.classList.add('growing');
                    if (progressWrapper) progressWrapper.classList.add('growing');
                }

                // Animate in
                setTimeout(() => {
                    indicator.classList.add('active');
                }, 50);

                // Start dynamic animations
                startDynamicAnimations(cardId);

                return indicator;
            }

            // ============================================
            // DYNAMIC PROGRESS ANIMATIONS
            // ============================================

            // Track animation state for each card
            const cardAnimationState = new Map();

            function startDynamicAnimations(cardId) {
                // Clear any existing animation state
                stopDynamicAnimations(cardId);

                const state = {
                    lastProgressUpdate: Date.now(),
                    isStuck: false,
                    intervals: []
                };

                cardAnimationState.set(cardId, state);

                // Check for stalled progress every 5 seconds
                const stuckCheckInterval = setInterval(() => {
                    const timeSinceUpdate = Date.now() - state.lastProgressUpdate;
                    const indicator = document.getElementById(`${cardId}-thinking`);
                    if (!indicator) {
                        clearInterval(stuckCheckInterval);
                        return;
                    }

                    const square = indicator.querySelector('.thinking-square, .progress-square');
                    if (!square) return;

                    // Speed up heartbeat if stuck for more than 10 seconds
                    if (timeSinceUpdate > 10000 && !state.isStuck) {
                        square.classList.add('stuck');
                        state.isStuck = true;
                    } else if (timeSinceUpdate <= 10000 && state.isStuck) {
                        square.classList.remove('stuck');
                        state.isStuck = false;
                    }
                }, 5000);

                state.intervals.push(stuckCheckInterval);

                // Animation cycle: rest → heartbeat speeds up → rotation → calm down → repeat
                const animationCycleInterval = setInterval(() => {
                    const indicator = document.getElementById(`${cardId}-thinking`);
                    if (!indicator) {
                        clearInterval(animationCycleInterval);
                        return;
                    }

                    const wrapper = indicator.querySelector('.progress-square-wrapper, .thinking-square-wrapper');
                    const square = indicator.querySelector('.progress-square, .thinking-square');
                    if (!wrapper || !square) return;

                    // Animation sequence:
                    // 0-2s: Rest (no rotation, normal heartbeat)
                    // 2-5s: Heartbeat speeds up gradually (3s ramp up)
                    // 5-7s: Fast heartbeat + rotation (2s of spinning)
                    // 7-10s: Calm down (stop rotation, slow heartbeat, 3s ramp down)
                    // Then immediately restart with rest phase

                    // Phase 1: Speed up heartbeat (after 2s rest)
                    setTimeout(() => {
                        square.classList.add('fast-heartbeat');

                        // Phase 2: Start rotation after heartbeat speeds up (3s later for gradual ramp)
                        setTimeout(() => {
                            // Remove growing animation to allow spinning to work (don't restore it to avoid re-triggering)
                            wrapper.classList.remove('growing');
                            wrapper.classList.add('spinning');

                            // Phase 3: Remove spinning class after animation completes (2s)
                            setTimeout(() => {
                                wrapper.classList.remove('spinning');

                                // Phase 4: Calm down heartbeat (3s longer ramp down)
                                setTimeout(() => {
                                    square.classList.remove('fast-heartbeat');
                                }, 3000);
                            }, 2000); // Animation is 2s
                        }, 3000);
                    }, 2000);

                }, 10000); // Full cycle: 2s rest + 3s speedup + 2s spin + 3s calm = 10s

                state.intervals.push(animationCycleInterval);
            }

            function stopDynamicAnimations(cardId) {
                const state = cardAnimationState.get(cardId);
                if (state) {
                    state.intervals.forEach(interval => clearInterval(interval));
                    cardAnimationState.delete(cardId);
                }
            }

            function updateProgressTimestamp(cardId) {
                const state = cardAnimationState.get(cardId);
                if (state) {
                    state.lastProgressUpdate = Date.now();

                    // Reset stuck state
                    if (state.isStuck) {
                        const indicator = document.getElementById(`${cardId}-thinking`);
                        if (indicator) {
                            const square = indicator.querySelector('.thinking-square, .progress-square');
                            if (square) {
                                square.classList.remove('stuck');
                            }
                        }
                        state.isStuck = false;
                    }
                }
            }

            function updateThinkingInCard(cardId, message) {
                const indicator = document.getElementById(`${cardId}-thinking`);
                if (indicator) {
                    const textEl = indicator.querySelector('.thinking-text');
                    if (textEl) textEl.textContent = message;
                }
                // Update timestamp to prevent stuck state
                updateProgressTimestamp(cardId);
            }
            
            // Dummy progress messages for when WebSocket is quiet
            const dummyProgressMessages = [
                { at: 5, message: "Initializing validation engine..." },
                { at: 10, message: "Loading configuration..." },
                { at: 15, message: "Analyzing table structure..." },
                { at: 20, message: "Preparing validation rules..." },
                { at: 25, message: "Starting row validation..." },
                { at: 30, message: "Validating data integrity..." },
                { at: 35, message: "Checking column constraints..." },
                { at: 40, message: "Processing validation targets..." },
                { at: 45, message: "Analyzing relationships..." },
                { at: 50, message: "Validating business rules..." },
                { at: 55, message: "Cross-referencing data..." },
                { at: 60, message: "Applying AI validation..." },
                { at: 65, message: "Checking data quality..." },
                { at: 70, message: "Running search group analysis..." },
                { at: 75, message: "Processing complex validations..." },
                { at: 80, message: "Executing final search groups..." },
                { at: 85, message: "Running final validation checks..." },
                { at: 90, message: "Completing search group processing..." },
                { at: 95, message: "Finalizing validation results..." }
            ];

            // Dummy progress messages for AI configuration generation
            const dummyConfigMessages = [
                { at: 5, message: "Starting AI configuration generation..." },
                { at: 15, message: "Analyzing table structure and data patterns..." },
                { at: 30, message: "Developing configuration with AI..." },
                { at: 40, message: "Negotiating validation details..." },
                { at: 50, message: "Optimizing search strategy..." },
                { at: 60, message: "Validating configuration structure..." },
                { at: 65, message: "Fine-tuning validation parameters..." },
                { at: 70, message: "AI configuration generated successfully!" },
                { at: 80, message: "Storing configuration..." },
                { at: 90, message: "Preparing download..." },
                { at: 95, message: "Finalizing configuration..." }
            ];

            // Track dummy progress for each card
            const cardDummyProgress = new Map();
            // Track current progress for each card to prevent going backward
            const cardCurrentProgress = new Map();

            function startDummyProgress(cardId, estimatedTime = 60000, messageType = 'processing') {
                // DISABLED: Dummy progress disabled to see real WebSocket messages
                return;
                
                // Original dummy progress code commented out:
                /*
                // Clear any existing dummy progress and reset progress tracking
                stopDummyProgress(cardId);
                cardCurrentProgress.set(cardId, 0);
                
                // Choose message set based on type
                const messages = messageType === 'config' ? dummyConfigMessages : dummyProgressMessages;
                
                const startTime = Date.now();
                const progressData = {
                    startTime,
                    estimatedTime,
                    lastMessageIndex: -1,
                    lastRealUpdate: Date.now(),
                    interval: null,
                    messageType,
                    messages
                };
                
                progressData.interval = setInterval(() => {
                    const elapsed = Date.now() - startTime;
                    const progress = Math.min(95, (elapsed / estimatedTime) * 100);
                    
                    // Only show dummy messages if we haven't had a real update in 3 seconds
                    if (Date.now() - progressData.lastRealUpdate > 3000) {
                        // Find appropriate dummy message
                        const messageIndex = messages.findIndex(m => m.at > progress) - 1;
                        if (messageIndex >= 0 && messageIndex !== progressData.lastMessageIndex) {
                            progressData.lastMessageIndex = messageIndex;
                            updateThinkingProgress(cardId, progress, messages[messageIndex].message);
                        }
                    }
                    
                    // Stop at 95% to wait for real completion
                    if (progress >= 95) {
                        clearInterval(progressData.interval);
                    }
                }, 500);
                
                cardDummyProgress.set(cardId, progressData);
                */
            }

            function stopDummyProgress(cardId) {
                const progressData = cardDummyProgress.get(cardId);
                if (progressData && progressData.interval) {
                    clearInterval(progressData.interval);
                    cardDummyProgress.delete(cardId);
                }
            }

            function markRealProgressUpdate(cardId) {
                const progressData = cardDummyProgress.get(cardId);
                if (progressData) {
                    progressData.lastRealUpdate = Date.now();
                }
            }

            function getConfidenceColor(confidenceScore) {
                /**
                 * Convert confidence score (0-100) to gradient color
                 * null/undefined -> green (default until confidence arrives)
                 * 0-50: red-yellow gradient
                 * 50-100: yellow-green gradient
                 */
                if (confidenceScore === null || confidenceScore === undefined) {
                    return '#2DFF45'; // Green default
                }

                // Clamp to 0-100 range
                confidenceScore = Math.max(0, Math.min(100, confidenceScore));

                let r, g, b;

                if (confidenceScore <= 50) {
                    // Red to Yellow gradient (0-50)
                    const t = confidenceScore / 50; // 0 to 1
                    r = 255;
                    g = Math.round(255 * t); // 0 to 255
                    b = 0;
                } else {
                    // Yellow to Green gradient (50-100)
                    const t = (confidenceScore - 50) / 50; // 0 to 1
                    r = Math.round(255 * (1 - t)); // 255 to 0
                    g = 255;
                    b = Math.round(69 * t); // 0 to 69 (matching #2DFF45)
                }

                return `rgb(${r}, ${g}, ${b})`;
            }

            // Track last message per card to prevent duplicates
            const cardLastProgressMessage = new Map();

            function updateThinkingProgress(cardId, progress, message = null) {
                const indicator = document.getElementById(`${cardId}-thinking`);
                if (!indicator || !indicator.classList.contains('with-progress')) return;

                // Deduplicate: skip if same message as last time for this card
                if (message) {
                    const lastMessage = cardLastProgressMessage.get(cardId);
                    if (lastMessage === message) {
                        // Same message, only update progress position, not text
                        console.log('[PROGRESS] Skipping duplicate message:', message.substring(0, 50));
                        message = null;
                    } else {
                        console.log('[PROGRESS] New message:', message.substring(0, 50));
                        cardLastProgressMessage.set(cardId, message);
                    }
                }

                // Mark that we got a real update
                markRealProgressUpdate(cardId);

                // Update dynamic animation timestamp
                updateProgressTimestamp(cardId);

                // Clamp progress between 0 and 100
                progress = Math.max(0, Math.min(100, progress));

                // Never go backward - use the maximum of current and new progress
                const currentProgress = cardCurrentProgress.get(cardId) || 0;
                const finalProgress = Math.max(currentProgress, progress);
                cardCurrentProgress.set(cardId, finalProgress);

                // Update progress square position (0% = left edge, 100% = right edge)
                const progressWrapper = indicator.querySelector('.progress-square-wrapper');
                const progressSquare = indicator.querySelector('.progress-square');
                const progressText = indicator.querySelector('.progress-text');
                const track = indicator.querySelector('.progress-track');

                if (progressWrapper && progressSquare && progressText && track) {
                    // Calculate position: 0% = left edge, 100% = right edge
                    const trackWidth = 120; // matches shorter CSS width
                    const wrapperOffset = 18.75; // half of 37.5px wrapper width to center it
                    const leftPosition = (finalProgress / 100) * trackWidth - wrapperOffset;

                    // Move the entire wrapper (black square + green center together)
                    progressWrapper.style.left = `${leftPosition}px`;

                    // Update message if provided (show WebSocket message, not percentage)
                    if (message) {
                        progressText.textContent = message;
                    }

                    // Apply confidence-based color (purple default until scores arrive)
                    requestAnimationFrame(() => {
                        const color = getConfidenceColor(globalState.currentConfidenceScore);
                        progressSquare.style.backgroundColor = color;
                    });
                }
            }

            function completeThinkingInCard(cardId, finalMessage = 'Complete!', hideDelay = 600) {
                // Stop any dummy progress and clean up progress tracking
                stopDummyProgress(cardId);
                cardCurrentProgress.delete(cardId);
                cardLastProgressMessage.delete(cardId); // Clean up message deduplication

                // Reset confidence score and history for next validation (return to green default)
                globalState.currentConfidenceScore = null;
                globalState.confidenceScores = [];

                // Stop dynamic animations
                stopDynamicAnimations(cardId);

                const indicator = document.getElementById(`${cardId}-thinking`);
                if (indicator) {
                    // Update message
                    updateThinkingInCard(cardId, finalMessage);

                    // Detect if this is an error message
                    const isError = finalMessage.toLowerCase().includes('failed') ||
                                   finalMessage.toLowerCase().includes('error') ||
                                   finalMessage.toLowerCase().includes('upload failed') ||
                                   finalMessage.toLowerCase().includes('generation failed') ||
                                   finalMessage.toLowerCase().includes('validation failed') ||
                                   finalMessage.toLowerCase().includes('refinement failed') ||
                                   finalMessage.toLowerCase().includes('preview failed') ||
                                   finalMessage.toLowerCase().includes('processing failed');

                    // Play appropriate animation
                    const square = indicator.querySelector('.thinking-square, .progress-square');
                    const wrapper = indicator.querySelector('.progress-square-wrapper');
                    const track = indicator.querySelector('.progress-track');

                    if (square) {
                        if (isError) {
                            square.classList.add('error');
                            if (wrapper) wrapper.classList.add('error');
                            square.style.animation = 'thinkingError 0.6s 1';
                        } else {
                            // For progress indicators, move to 100% first
                            if (indicator.classList.contains('with-progress')) {
                                updateThinkingProgress(cardId, 100);
                                setTimeout(() => {
                                    square.style.animation = 'thinkingComplete 0.6s 1';

                                    // Trigger progress bar shrink animation after completion
                                    setTimeout(() => {
                                        if (wrapper) wrapper.classList.add('shrinking');
                                        if (track) track.classList.add('shrinking');
                                    }, 600); // After completion animation
                                }, 300);
                            } else {
                                square.style.animation = 'thinkingComplete 0.6s 1';
                            }
                        }
                    }

                    // Hide after delay (extended if progress bar to allow shrink animation)
                    const totalDelay = indicator.classList.contains('with-progress') && !isError ? hideDelay + 1000 : hideDelay;
                    setTimeout(() => {
                        indicator.classList.remove('active');
                        setTimeout(() => {
                            indicator.remove();
                        }, 300);
                    }, totalDelay);
                }
            }

            function hideThinkingInCard(cardId) {
                // Stop dynamic animations
                stopDynamicAnimations(cardId);

                const indicator = document.getElementById(`${cardId}-thinking`);
                if (indicator) {
                    indicator.classList.remove('active');
                    setTimeout(() => {
                        indicator.remove();
                    }, 300);
                }
            }

            // ============================================
            // STANDARDIZED COMPONENTS
            // ============================================

            // Fix the card ID generation to avoid double incrementing
            function generateCardId() {
                return `card-${++globalState.cardCounter}`;
            }

            // SVG icon mapping - converts emoji/text to clean stroke SVG icons
            function getCardIconSvg(icon) {
                const svgIcons = {
                    // Table/Data icons
                    '📊': '<svg viewBox="0 0 24 24"><path d="M3 3h18v18H3z"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/></svg>',
                    '📈': '<svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-6"/></svg>',
                    '🔬': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 5v2"/><path d="M12 17v2"/><path d="M5 12h2"/><path d="M17 12h2"/></svg>',
                    // Action icons
                    '▶️': '<svg viewBox="0 0 24 24"><polygon points="6,4 20,12 6,20"/></svg>',
                    '🔄': '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>',
                    '↩️': '<svg viewBox="0 0 24 24"><path d="M9 14l-4-4 4-4"/><path d="M5 10h11a4 4 0 1 1 0 8h-1"/></svg>',
                    // File/Upload icons
                    '📥': '<svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
                    '📤': '<svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
                    '📁': '<svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
                    '📄': '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
                    // Settings/Config icons
                    '⚙️': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4"/><path d="M12 19v4"/><path d="M4.22 4.22l2.83 2.83"/><path d="M16.95 16.95l2.83 2.83"/><path d="M1 12h4"/><path d="M19 12h4"/><path d="M4.22 19.78l2.83-2.83"/><path d="M16.95 7.05l2.83-2.83"/></svg>',
                    '🔧': '<svg viewBox="0 0 24 24"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
                    // Communication icons
                    '✉️': '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>',
                    '🔐': '<svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
                    // Status/Result icons
                    '✨': '<svg viewBox="0 0 24 24"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M5 19l.5 1.5L7 21l-1.5.5L5 23l-.5-1.5L3 21l1.5-.5L5 19z"/></svg>',
                    '🎉': '<svg viewBox="0 0 24 24"><path d="M5.8 11.3 2 22l10.7-3.8"/><path d="M11 13c1.93 1.93 2.83 4.17 2 5-.83.83-3.07-.07-5-2-1.93-1.93-2.83-4.17-2-5 .83-.83 3.07.07 5 2z"/></svg>',
                    '💳': '<svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
                    '✅': '<svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
                    // View/Search icons
                    '👁️': '<svg viewBox="0 0 24 24"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>',
                    '🔍': '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
                    '⚡': '<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
                    // Misc icons
                    '🚀': '<svg viewBox="0 0 24 24"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>',
                    '🤖': '<svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><circle cx="8" cy="16" r="1"/><circle cx="16" cy="16" r="1"/></svg>',
                    '🎯': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
                    // Default fallback
                    'default': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>'
                };

                // Try exact match first, then try without variation selector
                if (svgIcons[icon]) return svgIcons[icon];

                // Strip variation selectors (️ = \uFE0F) and try again
                const stripped = icon.replace(/\uFE0F/g, '');
                if (svgIcons[stripped]) return svgIcons[stripped];

                return svgIcons['default'];
            }

            // Update createCard to handle explicit ID
            function createCard(options) {
                const {
                    icon,
                    title,
                    subtitle,
                    content = '',
                    statusBadge = null,
                    buttons = [],
                    id = null  // Allow explicit ID
                } = options;

                // Use provided ID or generate new one
                const cardId = id || generateCardId();
                
                const card = document.createElement('div');
                card.className = 'card';
                card.id = cardId;
                
                // Build card HTML - ALWAYS include buttons container
                let cardHtml = `
                    <div class="card-header">
                        <div class="card-icon">${icon ? getCardIconSvg(icon) : globalState.cardCounter}</div>
                        <div>
                            <h2 class="card-title">${title}</h2>
                            ${subtitle ? `<p class="card-subtitle">${subtitle}</p>` : ''}
                        </div>
                        ${statusBadge ? `
                            <div class="status-badge ${statusBadge.type}">
                                <span>${statusBadge.text}</span>
                            </div>
                        ` : ''}
                    </div>
                    <div class="card-content">${content}</div>
                    <div id="${cardId}-buttons" class="card-buttons"></div>
                `;

                card.innerHTML = cardHtml;

                // Add to container
                document.getElementById('cardContainer').appendChild(card);

                // Verify buttons container exists
                const buttonsContainer = document.getElementById(`${cardId}-buttons`);

                // Add buttons if any provided
                if (buttons.length > 0) {
                    // Use requestAnimationFrame instead of setTimeout for better performance
                    requestAnimationFrame(() => {
                        createButtonRow(`${cardId}-buttons`, buttons);
                    });
                }

                // Scroll to view - defer to avoid forced reflow, but skip for first card to allow reading content above
                if (globalState.cardCounter > 1) {
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => {
                            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        });
                    });
                }

                return card;
            }

            // Create standardized button row
            function createButtonRow(containerId, buttons) {
                const container = document.getElementById(containerId);
                if (!container) {
                    console.error(`Button container ${containerId} not found`);
                    // Try to find the card and create the container
                    const cardId = containerId.replace('-buttons', '');
                    const card = document.getElementById(cardId);
                    if (card) {
                        const buttonsDiv = document.createElement('div');
                        buttonsDiv.id = containerId;
                        buttonsDiv.className = 'card-buttons';
                        card.appendChild(buttonsDiv);
                        // Try again
                        return createButtonRow(containerId, buttons);
                    }
                    return;
                }

                // Clear any existing content
                container.innerHTML = '';

                const buttonRow = document.createElement('div');
                buttonRow.className = 'button-row';

                // For single full-width buttons, remove centering
                if (buttons.length === 1 && buttons[0].width === 'full') {
                    buttonRow.style.justifyContent = 'stretch';
                }

                // Color cycle: green, purple, orange, cyan, pink
                const colorCycle = ['primary', 'secondary', 'tertiary', 'quaternary', 'quinary'];

                buttons.forEach((btnConfig, index) => {
                    const button = document.createElement('button');
                    // Use explicit variant if provided, otherwise cycle through colors
                    // Calculate index from the end so the last button is always green (primary)
                    let variant;
                    if (btnConfig.variant) {
                        variant = btnConfig.variant;
                    } else {
                        // Calculate position from the end: last button = 0, second-to-last = 1, etc.
                        const positionFromEnd = buttons.length - 1 - index;
                        // Map to color cycle in reverse: last=primary, second-to-last=quinary, etc.
                        const colorIndex = positionFromEnd % 5;
                        variant = colorCycle[colorIndex];
                    }
                    button.className = `std-button ${variant}`;
                    if (btnConfig.width === 'full') {
                        button.style.width = '100%';
                        button.style.flex = 'none';
                    } else {
                        button.style.flex = btnConfig.width || 1;
                    }
                    button.innerHTML = `
                        <span class="button-text">${btnConfig.icon || ''} ${btnConfig.text}</span>
                        <span class="spinner"></span>
                    `;

                    button.onclick = async (e) => {
                        if (button.disabled) return;

                        // Show loading state
                        button.classList.add('loading');
                        button.disabled = true;

                        try {
                            await btnConfig.callback(e);
                        } catch (error) {
                            console.error('Button callback error:', error);
                            // Show error state on button
                            button.classList.add('error');
                            button.innerHTML = `
                                <span class="button-text">[ERROR] Error</span>
                                <span class="spinner"></span>
                            `;
                            // Reset after delay
                            setTimeout(() => {
                                button.classList.remove('error', 'loading');
                                button.disabled = false;
                                button.innerHTML = `
                                    <span class="button-text">${btnConfig.icon || ''} ${btnConfig.text}</span>
                                    <span class="spinner"></span>
                                `;
                            }, 3000);
                        } finally {
                            // Always remove loading state unless button was marked as selected or errored
                            if (!button.classList.contains('selected') && !button.classList.contains('error')) {
                                button.classList.remove('loading');
                                button.disabled = false;
                            }
                        }
                    };

                    if (btnConfig.disabled) {
                        button.disabled = true;
                    }

                    buttonRow.appendChild(button);
                });

                container.appendChild(buttonRow);
            }

            // Mark button as selected (past choice) - Fixed to not interfere with loading state
            function markButtonSelected(buttonElement, newText) {
                // Remove loading state first
                buttonElement.classList.remove('loading');
                // Add selected state
                buttonElement.classList.add('selected');
                buttonElement.disabled = true;
                if (newText) {
                    // Try to find .button-text first (standard buttons)
                    const buttonTextElement = buttonElement.querySelector('.button-text');
                    if (buttonTextElement) {
                        buttonTextElement.textContent = newText;
                    } else {
                        // Fallback: set the entire button content for demo buttons and others
                        buttonElement.innerHTML = `<span>${newText}</span>`;
                    }
                }
                // Disable all sibling buttons
                const siblings = buttonElement.parentElement.querySelectorAll('.std-button');
                siblings.forEach(btn => {
                    if (btn !== buttonElement) {
                        btn.disabled = true;
                        btn.style.opacity = '0.5';
                    }
                });
            }

            function markButtonUnselected(buttonElement) {
                // Remove selected state
                buttonElement.classList.remove('selected', 'loading');
                buttonElement.disabled = false;
                buttonElement.style.opacity = '';
                
                // Re-enable all sibling buttons
                const siblings = buttonElement.parentElement.querySelectorAll('.std-button');
                siblings.forEach(btn => {
                    btn.disabled = false;
                    btn.style.opacity = '';
                });
            }
            
            function resetProcessButtons() {
                // Use global state values
                const currentBalance = globalState.accountBalance || 0;
                const estimatedCost = globalState.estimatedCost || 0;
                const effectiveCost = globalState.effectiveCost ?? estimatedCost; // Use ?? not || so 0 doesn't fall back
                const creditsNeeded = Math.max(0, effectiveCost - currentBalance);
                const sufficientBalance = currentBalance >= effectiveCost;

                // Find all buttons that need updating
                const buttons = document.querySelectorAll('button');
                buttons.forEach(button => {
                    const buttonText = button.textContent || '';

                    // Check if this is a credits/process button
                    if (buttonText.includes('💳') || buttonText.includes('Add') && buttonText.includes('Credits') ||
                        buttonText.includes('Process Table') || buttonText.includes('Opening store')) {

                        // Check if it's in a preview card
                        const card = button.closest('.card');
                        if (card && (card.textContent.includes('Your Balance') || card.textContent.includes('Est. Cost'))) {
                            // Reset button state
                            markButtonUnselected(button);

                            if (sufficientBalance) {
                                // Show process button with cost
                                button.innerHTML = `<span class="button-text">🔍 Process Table ($${effectiveCost.toFixed(2)})</span>`;
                                button.className = 'std-button primary';
                                button.setAttribute('data-action', 'process');
                                
                                button.onclick = async (e) => {
                                    const btn = e.target.closest('button');
                                    markButtonSelected(btn, '✨ Processing...');
                                    globalState.activePreviewCard = null;
                                    createProcessingCard();
                                };
                            } else {
                                // Show add credits button with remaining amount needed
                                button.innerHTML = `<span class="button-text">💳 Add $${creditsNeeded.toFixed(2)} Credits</span>`;
                                button.className = 'std-button secondary';
                                button.setAttribute('data-action', 'process');
                                
                                button.onclick = async (e) => {
                                    const btn = e.target.closest('button');
                                    globalState.hasInsufficientBalance = true;
                                    markButtonSelected(btn, '💳 Opening store...');
                                    const recommendedAmount = Math.ceil(creditsNeeded);
                                    const cardId = card.querySelector('[id*="preview"]')?.id?.replace('-content', '');
                                    openAddCreditsPage(recommendedAmount, `${cardId}-messages`);
                                };
                            }
                        }
                    }
                });
            }

            // Show preview results - with debugging
            function showPreviewResults(cardId, previewData) {
                // Save preview data globally for restoration
                window.lastPreviewData = previewData;

                // Mark preview as completed
                ensureProcessingState();
                globalState.processingState.previewCompleted = true;
                
                // Hide progress, show results
                const resultsEl = document.getElementById(`${cardId}-results`);
                if (!resultsEl) {
                    console.error(`Results element ${cardId}-results not found`);
                    return;
                }
                resultsEl.style.display = 'block';

                // Render markdown table with blue info header
                const previewContent = document.getElementById(`${cardId}-preview-content`);
                if (previewContent && previewData.markdown_table) {
                    // Generate download URL for full preview
                    let fullPreviewUrl = '#';
                    if (previewData.enhanced_download_url) {
                        fullPreviewUrl = previewData.enhanced_download_url;
                    } else if (previewData.full_preview_url) {
                        fullPreviewUrl = previewData.full_preview_url;
                    } else if (globalState.sessionId) {
                        // Generate preview download URL based on session
                        fullPreviewUrl = `${API_BASE}/download/${globalState.sessionId}/preview_results.xlsx`;
                    }
                    
                    const headerHtml = `
                        <div class="message message-info">
                            <span class="message-icon">ℹ️</span>
                            <span>Preview of first 3 rows (displayed as columns). Hover cells for quick info, click for full details. Use the buttons below to download, refine, or process the full table.</span>
                        </div>
                    `;
                    
                    previewContent.innerHTML = headerHtml + renderMarkdown(previewData.markdown_table);
                    
                    // Store the download URL for the button
                    previewContent.dataset.fullPreviewUrl = fullPreviewUrl;
                }

                // Add buttons above estimates
                // Check if revert button should be shown (only if this session has 2+ versions)
                // Use session_version_count if available (accurate), otherwise fall back to config_version
                const sessionVersionCount = previewData.session_version_count || 0;
                const currentVersion = previewData.config_version || globalState.currentConfig?.config_version || 1;
                const showRevertButton = sessionVersionCount >= 2;

                const revertButtonHtml = showRevertButton ?
                    `<button type="button" class="std-button quaternary" data-action="revert-config">
                            ↩️ Revert to Previous
                        </button>` : '';

                // Fixed colors for preview card buttons
                // Download = orange, Refine = purple, Revert = cyan (when shown), Process = green
                const downloadColor = 'tertiary';  // orange
                const refineColor = 'secondary';   // purple

                // Hide refine button for reference check (static config cannot be refined)
                const refineButtonHtml = !globalState.isReferenceCheck ?
                    `<button type="button" class="std-button ${refineColor}" data-action="refine-config">
                        🔧 Refine Configuration
                    </button>` : '';

                const actionsHtml = `
                    <div style="display: flex; gap: 10px; margin-bottom: 20px; justify-content: center;">
                        <button type="button" class="std-button ${downloadColor}" data-action="download-preview">
                            📥 Download Excel Preview
                        </button>
                        ${refineButtonHtml}
                        ${revertButtonHtml}
                    </div>
                `;
                previewContent.innerHTML += actionsHtml;

                // Calculate cost values ONCE before display and button logic to ensure consistency
                const estimatedCost = previewData.cost_estimates ? (previewData.cost_estimates.quoted_validation_cost || previewData.cost_estimates.quoted_full_cost) : 0;
                const discount = previewData.cost_estimates?.discount || previewData.discount || 0;
                const effectiveCost = previewData.cost_estimates?.effective_cost !== undefined
                    ? previewData.cost_estimates.effective_cost
                    : Math.max(0, estimatedCost - discount);
                const accountInfo = previewData.account_info;
                const currentBalance = accountInfo?.current_balance || 0;
                // TRUST THE BACKEND - use its balance calculations, don't recalculate
                const sufficientBalance = accountInfo?.sufficient_balance ?? true;
                const creditsNeeded = accountInfo?.credits_needed || 0;

                // Store in global state for later use
                globalState.estimatedCost = estimatedCost;
                globalState.discount = discount;
                globalState.effectiveCost = effectiveCost;
                globalState.accountInfo = accountInfo;

                // Show cost estimates
                if (previewData.cost_estimates && previewData.validation_metrics) {
                    const costEl = document.getElementById(`${cardId}-cost-estimate`);
                    const estimatesEl = document.getElementById(`${cardId}-estimates`);

                    if (costEl && estimatesEl) {
                        costEl.style.display = 'block';

                        const metrics = previewData.validation_metrics;
                        const totalRows = previewData.total_rows || 0;
                        const estimatedTime = previewData.cost_estimates.estimated_validation_time || 0;
                        
                        let estimatesHtml = '';
                        
                        if (totalRows > 0) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Total Rows</span><span class="cost-value">${totalRows.toLocaleString()}</span></div>`;
                        }
                        
                        if (metrics.validated_columns_count) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Columns to Validate</span><span class="cost-value">${metrics.validated_columns_count}</span></div>`;
                        }
                        
                        // Show total AI calls (validation + QC calls)
                        // Clone counts as 1 call even if it makes multiple internal calls
                        const totalSearchGroups = metrics.search_groups_count || 0;
                        const qcCallsPerRow = metrics.qc_calls_per_row || 0;

                        // DEBUG: Log the values being used
                        console.log('[AI_CALLS_CALC] validation_metrics:', metrics);
                        console.log('[AI_CALLS_CALC] totalRows:', totalRows);
                        console.log('[AI_CALLS_CALC] search_groups_count:', totalSearchGroups);
                        console.log('[AI_CALLS_CALC] qc_calls_per_row:', qcCallsPerRow);

                        if (totalSearchGroups > 0 || qcCallsPerRow > 0) {
                            // Total AI calls = (validation calls per row + QC calls per row) × total rows
                            const callsPerRow = totalSearchGroups + qcCallsPerRow;
                            const totalAICalls = totalRows * callsPerRow;
                            console.log('[AI_CALLS_CALC] callsPerRow:', callsPerRow, '(groups:', totalSearchGroups, '+ QC:', qcCallsPerRow, ')');
                            console.log('[AI_CALLS_CALC] totalAICalls:', totalAICalls, '(', totalRows, '×', callsPerRow, ')');
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Total AI Calls</span><span class="cost-value">${totalAICalls.toLocaleString()}</span></div>`;
                        }
                        
                        estimatesHtml += `<div class="cost-item"><span class="cost-label">Est. Time</span><span class="cost-value">${Math.ceil(estimatedTime / 60)} min</span></div>`;

                        // Display cost with discount if applicable (using pre-calculated values)
                        if (discount > 0) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost → Discounted</span><span class="cost-value"><span style="text-decoration: line-through; color: #999;">$${estimatedCost.toFixed(2)}</span> → $${effectiveCost.toFixed(2)}</span></div>`;
                        } else {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost</span><span class="cost-value">$${estimatedCost.toFixed(2)}</span></div>`;
                        }
                        
                        // Domain multiplier is hidden from frontend display
                        
                        // Add account balance information if available (using pre-calculated values)
                        if (accountInfo) {
                            estimatesHtml += `<hr style="margin: 10px 0; border: none; border-top: 1px solid #eee;">`;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Your Balance</span><span class="cost-value">$${currentBalance.toFixed(2)}</span></div>`;

                            if (!sufficientBalance && creditsNeeded > 0) {
                                estimatesHtml += `<div class="cost-item"><span class="cost-label" style="color: #f44336;">Credits Needed</span><span class="cost-value" style="color: #f44336;">$${creditsNeeded.toFixed(2)}</span></div>`;
                            }
                        }

                        estimatesEl.innerHTML = estimatesHtml;
                        
                    }
                }

                const card = document.getElementById(cardId);

                // Values already calculated above and stored in outer scope, ready for use

                // Add event listeners for the buttons above estimates
                setTimeout(() => {
                    const downloadBtn = card.querySelector('[data-action="download-preview"]');
                    const refineBtn = card.querySelector('[data-action="refine-config"]');
                    const revertBtn = card.querySelector('[data-action="revert-config"]');

                    if (downloadBtn) {
                        downloadBtn.addEventListener('click', async () => {
                            markDownloadStart();
                            await downloadPreviewResults(previewData);
                        });
                    }

                    if (refineBtn) {
                        refineBtn.addEventListener('click', debounceConfigAction('refine-config', async () => {
                            // Don't use markButtonSelected as it expects different button structure
                            refineBtn.disabled = true;
                            refineBtn.textContent = '🔧 Refining...';
                            globalState.activePreviewCard = null;
                            await createRefinementCard();
                        }));
                    }

                    // Only add revert button listener if the button exists (version > 1)
                    if (revertBtn) {
                        revertBtn.addEventListener('click', debounceConfigAction('revert-config', async () => {
                            revertBtn.disabled = true;
                            revertBtn.textContent = '↩️ Reverting...';
                            globalState.activePreviewCard = null;
                            await createConfigCardWithId('last');
                        }));
                    }
                }, 100);

                // Show single Process Table button at bottom
                // Calculate discount and effectiveCost from preview data (recalculate to ensure we have fresh values)
                const buttonDiscount = previewData.cost_estimates?.discount || previewData.discount || 0;
                const buttonEffectiveCost = previewData.cost_estimates?.effective_cost !== undefined
                    ? previewData.cost_estimates.effective_cost
                    : Math.max(0, estimatedCost - buttonDiscount);

                let buttonCostText = '';
                if (estimatedCost) {
                    if (buttonDiscount > 0) {
                        // Show strikethrough original cost → discounted price (same format as cost display)
                        buttonCostText = ` (<span style="text-decoration: line-through;">$${estimatedCost.toFixed(2)}</span> → $${buttonEffectiveCost.toFixed(2)})`;
                    } else {
                        buttonCostText = ` ($${estimatedCost.toFixed(2)})`;
                    }
                }

                createButtonRow(`${cardId}-buttons`, [
                    {
                        text: sufficientBalance
                            ? `Process Table${buttonCostText}`
                            : `Add Credits ($${Math.ceil(creditsNeeded).toFixed(2)})`,
                        icon: sufficientBalance ? '✨' : '💳',
                        variant: sufficientBalance ? 'primary' : 'secondary',
                        width: 'full',
                        callback: async (e) => {
                            const button = e.target.closest('button');

                            if (sufficientBalance) {
                                // User has sufficient balance - proceed with processing
                                globalState.hasInsufficientBalance = false;
                                markButtonSelected(button, '✨ Processing...');
                                globalState.activePreviewCard = null;
                                createProcessingCard();
                            } else {
                                // Insufficient balance - open add credits page
                                globalState.hasInsufficientBalance = true;
                                // Mark that user attempted processing from preview
                                globalState.userAttemptedProcessing = true;
                                globalState.pendingProcessingTrigger = () => {
                                    // console.trace('[AUTO-TRIGGER] Stack trace:');
                                    globalState.activePreviewCard = null;

                                    // Find and click the Process Table button to trigger normal processing
                                    const buttons = document.querySelectorAll('button');
                                    for (const button of buttons) {
                                        const buttonText = button.querySelector('.button-text, span');
                                        if (buttonText && buttonText.textContent.includes('Process Table')) {
                                            button.click();
                                            break;
                                        }
                                    }
                                };
                                markButtonSelected(button, '💳 Opening store...');
                                // Use effective cost-based creditsNeeded (already calculated above using effectiveCost)
                                const recommendedAmount = Math.ceil(creditsNeeded); // Round up to nearest dollar
                                openAddCreditsPage(recommendedAmount, `${cardId}-messages`);

                                // Reset button after a delay
                                setTimeout(() => {
                                    markButtonUnselected(button);
                                }, 2000);
                            }
                        }
                    }
                ]);

                // Show instruction message for Add Credits button
                if (!sufficientBalance) {
                    showMessage(`${cardId}-messages`, `💳 Click button to add credits. After purchase, return to this tab for auto-processing.`, 'info', false, 'add-credits-instruction');
                }
            }
            // Create standardized progress component
            function createProgress(options) {
                const {
                    title = 'Processing...',
                    messages = ['Starting...', 'Working...', 'Almost done...'],
                    estimatedTime = 30000,
                    containerId,
                    useWebSocket = false
                } = options;

                const progressId = `progress-${Date.now()}`;
                const progressHtml = `
                    <div class="progress-container" id="${progressId}">
                        <div class="progress-title">${title}</div>
                        <div class="progress-message">${messages[0]}</div>
                        <div class="progress-bar-wrapper">
                            <div class="progress-bar-fill"></div>
                        </div>
                        <div class="progress-percentage">0%</div>
                    </div>
                `;

                if (containerId) {
                    const container = document.getElementById(containerId);
                    if (container) {
                        container.insertAdjacentHTML('beforeend', progressHtml);
                    }
                }

                const progressEl = document.getElementById(progressId);
                const messageEl = progressEl.querySelector('.progress-message');
                const barEl = progressEl.querySelector('.progress-bar-fill');
                const percentEl = progressEl.querySelector('.progress-percentage');

                let progress = 0;
                let messageIndex = 0;
                let interval = null;
                let isCompleted = false;

                const updateProgress = (percent, message) => {
                    if (isCompleted) return;
                    
                    progress = Math.min(percent, 100);
                    barEl.style.width = `${progress}%`;
                    percentEl.textContent = `${Math.round(progress)}%`;
                    if (message) messageEl.textContent = message;
                };

                const startAutoProgress = () => {
                    if (useWebSocket) return;
                    
                    const increment = 100 / (estimatedTime / 100);
                    interval = setInterval(() => {
                        if (progress < 75) {
                            progress += increment;
                            updateProgress(progress);
                            
                            const newMessageIndex = Math.floor((progress / 75) * messages.length);
                            if (newMessageIndex > messageIndex && newMessageIndex < messages.length) {
                                messageIndex = newMessageIndex;
                                messageEl.textContent = messages[messageIndex];
                            }
                        }
                    }, 100);
                };

                const stopAutoProgress = () => {
                    if (interval) {
                        clearInterval(interval);
                        interval = null;
                    }
                };

                const complete = (finalMessage) => {
                    isCompleted = true;
                    stopAutoProgress();
                    updateProgress(100, finalMessage || 'Complete!');
                    
                    // Add error styling if message indicates failure
                    if (finalMessage && finalMessage.includes('❌')) {
                        barEl.style.backgroundColor = '#f44336'; // Red color for errors
                        messageEl.style.color = '#f44336';
                        percentEl.style.color = '#f44336';
                    }
                    
                    setTimeout(() => {
                        if (progressEl && progressEl.parentElement) {
                            progressEl.style.opacity = '0';
                            setTimeout(() => progressEl.remove(), 300);
                        }
                    }, 1000);
                };

                if (!useWebSocket) {
                    // startAutoProgress(); // DISABLED to see real progress
                }

                return {
                    element: progressEl,
                    updateProgress,
                    complete,
                    setMessage: (msg) => { messageEl.textContent = msg; },
                    stopAutoProgress,
                    isWebSocketMode: useWebSocket
                };
            }

            // Run operation with progress
            async function runWithProgress(operation, progressOptions) {
                const progress = createProgress(progressOptions);
                
                try {
                    const result = await operation(progress);
                    progress.complete();
                    return result;
                } catch (error) {
                    progress.complete('Error occurred');
                    throw error;
                }
            }

