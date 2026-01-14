/* ========================================
 * 10-upload-interview.js - Upload Interview Flow
 *
 * Handles PDF upload and interview conversations
 * for table configuration.
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */

        async function handlePdfUpload(cardId, file) {
const messagesDiv = document.getElementById(`${cardId}-messages`);

try {
    // Validate file type
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        completeThinkingInCard(cardId, 'Invalid file type');
        showMessage(messagesDiv.id, 'Please select a PDF file', 'error');
        return;
    }

    // Validate file size (50MB max - no longer limited by API Gateway!)
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
        completeThinkingInCard(cardId, 'File too large');
        showMessage(messagesDiv.id, `PDF file too large. Maximum size is ${maxSize / 1024 / 1024}MB`, 'error');
        return;
    }

    // Show initial progress
    showThinkingInCard(cardId, `Preparing to upload ${file.name}...`, true);

    // Step 1: Request presigned URL from backend
    const presignedResponse = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'requestPresignedUrl',
            file_type: 'pdf',
            filename: file.name,
            file_size: file.size,
            email: globalState.email,
            session_id: globalState.sessionId || ''
        })
    });

    const presignedData = await presignedResponse.json();

    if (!presignedResponse.ok || !presignedData.success) {
        throw new Error(presignedData.message || 'Failed to get upload URL');
    }

    // Store upload ID and session ID
    const uploadId = presignedData.upload_id;
    const s3Key = presignedData.s3_key;
    const sessionId = presignedData.session_id;

    // Store session_id if backend generated one
    if (sessionId && !globalState.sessionId) {
        globalState.sessionId = sessionId;
        localStorage.setItem('sessionId', sessionId);
    }

    referenceCheckState.pdfId = uploadId;
    referenceCheckState.pdfFilename = file.name;

    // Update progress
    showThinkingInCard(cardId, `Uploading ${file.name} to secure storage...`, true);

    // Step 2: Upload file directly to S3 using presigned URL
    // IMPORTANT: Include metadata as x-amz-meta-* headers to match presigned URL params
    const uploadResponse = await fetch(presignedData.presigned_url, {
        method: 'PUT',
        body: file,
        headers: {
            'Content-Type': presignedData.content_type,  // Use content type from backend
            'x-amz-meta-upload_id': uploadId,
            'x-amz-meta-original_filename': file.name,
            'x-amz-meta-email': globalState.email,
            'x-amz-meta-session_id': sessionId,
            'x-amz-meta-file_type': 'pdf',
            'x-amz-meta-file_size': file.size.toString(),
            'x-amz-meta-uploaded_at': new Date().toISOString()
        }
    });

    if (!uploadResponse.ok) {
        throw new Error(`Upload failed with status ${uploadResponse.status}`);
    }

    console.log('[PDF_UPLOAD] File uploaded to S3 successfully');

    // Step 3: Confirm upload complete and trigger processing
    const confirmResponse = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'confirmUploadComplete',
            upload_id: uploadId,
            s3_key: s3Key,
            session_id: sessionId,
            file_type: 'pdf',
            filename: file.name,
            email: globalState.email
        })
    });

    const confirmData = await confirmResponse.json();

    if (!confirmResponse.ok || !confirmData.success) {
        throw new Error(confirmData.message || 'Failed to confirm upload');
    }

    // Show progress indicator and wait for WebSocket updates
    showThinkingInCard(cardId, `${file.name} uploaded successfully. Reading PDF...`, true);

    // Connect to WebSocket to receive conversion result
    connectToSession(sessionId);

    // Register WebSocket handler for PDF conversion
    unregisterCardHandler(cardId);
    registerCardHandler(cardId, ['pdf_conversion_progress', 'pdf_conversion_complete', 'pdf_conversion_error'], (wsData) => {
        handlePdfConversionMessage(cardId, wsData, file.name);
    });

} catch (error) {
    console.error('[PDF_UPLOAD] Error:', error);
    completeThinkingInCard(cardId, 'Upload failed');
    showMessage(messagesDiv.id,
        `Error uploading PDF: ${error.message}`,
        'error'
    );
}
        }

        // Handle file picker cancel for PDF upload
        document.addEventListener('focus', () => {
if (referenceCheckState.awaitingPdfSelection) {
    // User may have cancelled file picker - check after a short delay
    setTimeout(() => {
        if (referenceCheckState.awaitingPdfSelection) {
            // File picker was cancelled (no file selected)
            const cardId = referenceCheckState.cardId;
            referenceCheckState.awaitingPdfSelection = false;

            // Recreate the card to restore buttons
            createReferenceCheckCard();
        }
    }, 500);
}
        }, true);

        // Handle PDF conversion WebSocket messages
        function handlePdfConversionMessage(cardId, message, filename) {
console.log('[PDF_CONVERSION] Received message:', message.type);

if (message.type === 'pdf_conversion_progress') {
    // Update progress indicator (like table maker)
    const progressMsg = message.message || 'Converting PDF...';
    updateThinkingInCard(cardId, progressMsg);

    // Update progress bar if percentage provided
    if (message.progress !== undefined) {
        updateThinkingProgress(cardId, message.progress, progressMsg);
    }
}
else if (message.type === 'pdf_conversion_complete') {
    // PDF converted and claim extraction started automatically
    updateThinkingInCard(cardId, `${filename} converted. Extracting claims from text (this may take a minute)...`);

    // Store conversation ID for reference check tracking
    referenceCheckState.conversationId = message.conversation_id;

    // Unregister PDF conversion handler, now listen for reference check progress
    unregisterCardHandler(cardId);
    registerCardHandler(cardId, ['reference_check_progress', 'reference_check_complete', 'reference_check_error'], (wsData) => {
        if (wsData.type === 'reference_check_progress') {
            handleReferenceCheckProgress(wsData, cardId);
        } else if (wsData.type === 'reference_check_complete') {
            handleReferenceCheckComplete(wsData, cardId);
        } else if (wsData.type === 'reference_check_error') {
            handleReferenceCheckError(wsData, cardId);
        }
    });
}
else if (message.type === 'pdf_conversion_error') {
    // Show error
    completeThinkingInCard(cardId, `Error: ${message.message}`);

    // Clean up WebSocket handler
    unregisterCardHandler(cardId);
}
        }

        // Start reference check
        async function startReferenceCheck(cardId) {
const input = document.getElementById(`${cardId}-input`);
const submittedText = input.value.trim();

// Store submitted text (validation already done in button callback)
referenceCheckState.submittedText = submittedText;

// Update thinking indicator (already shown by callback as "Submitting text...")
updateThinkingInCard(cardId, 'Text submitted. Extracting claims from text (this may take a minute)...');

// Register WebSocket handler
registerCardHandler(cardId, ['reference_check_progress', 'reference_check_complete', 'reference_check_error'], (data) => {
    if (data.type === 'reference_check_progress') {
        handleReferenceCheckProgress(data, cardId);
    } else if (data.type === 'reference_check_complete') {
        handleReferenceCheckComplete(data, cardId);
    } else if (data.type === 'reference_check_error') {
        handleReferenceCheckError(data, cardId);
    }
});

// Send API request
try {
    const response = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'startReferenceCheck',
            email: globalState.email,
            session_id: globalState.sessionId || null,
            submitted_text: submittedText
        })
    });

    const data = await response.json();

    if (data.success && data.status === 'processing') {
        // Request queued successfully
        referenceCheckState.conversationId = data.conversation_id;

        // Store session_id if backend generated one
        if (data.session_id && !globalState.sessionId) {
            globalState.sessionId = data.session_id;
            localStorage.setItem('sessionId', data.session_id);
        }

        // Connect to WebSocket session
        connectToSession(globalState.sessionId);
    } else if (data.error === 'text_too_large') {
        // Handle text too large error
        completeThinkingInCard(cardId, 'Text too large');
        showMessage(`${cardId}-messages`,
            `Text is too large (${data.char_count} characters). Maximum allowed is ${data.max_chars} characters (approximately ${data.max_words} words).`,
            'error');

        // Re-enable textarea
        input.value = submittedText;
        input.rows = 12;
        input.disabled = false;
        input.style.cursor = 'text';
    } else {
        completeThinkingInCard(cardId, 'Failed to start');
        showMessage(`${cardId}-messages`,
            'Failed to start reference check: ' + (data.error || data.message || 'Unknown error'),
            'error');

        // Re-enable textarea
        input.value = submittedText;
        input.rows = 12;
        input.disabled = false;
        input.style.cursor = 'text';
    }
} catch (error) {
    console.error('Error starting reference check:', error);
    completeThinkingInCard(cardId, 'Error');
    showMessage(`${cardId}-messages`,
        'Failed to start reference check. Please try again.',
        'error');

    // Re-enable textarea
    input.value = submittedText;
    input.rows = 12;
    input.disabled = false;
    input.style.cursor = 'text';
}
        }

        // Handle reference check progress updates
        function handleReferenceCheckProgress(data, cardId) {
// Use cardId from referenceCheckState if not provided
if (!cardId) {
    cardId = referenceCheckState.cardId;
}
if (!cardId) return;

// Update progress bar
if (data.progress !== undefined) {
    const message = data.message || data.status || 'Processing...';
    updateThinkingProgress(cardId, data.progress, message);
}

// Show claims found if available
if (data.claims_found !== undefined) {
    updateThinkingInCard(cardId, `Found ${data.claims_found} claims to validate...`);
}

// Show validation progress if available
if (data.claims_validated !== undefined && data.total_claims !== undefined) {
    updateThinkingInCard(cardId, `Validated ${data.claims_validated} of ${data.total_claims} claims...`);
}
        }

        // Handle reference check complete
        function handleReferenceCheckComplete(data, cardId) {
// Use cardId from referenceCheckState if not provided
if (!cardId) {
    cardId = referenceCheckState.cardId;
}
if (!cardId) return;

// Store data in global state (like table_maker does)
if (data.csv_s3_key) globalState.csvS3Key = data.csv_s3_key;
if (data.config_s3_key) globalState.configS3Key = data.config_s3_key;
if (data.session_id) {
    globalState.sessionId = data.session_id;
    localStorage.setItem('sessionId', data.session_id);
}

// Mark files as ready for validation
globalState.configValidated = true;
globalState.configStored = true;
globalState.excelFileUploaded = true;

// Mark as reference check session (config is static, cannot be refined)
globalState.isReferenceCheck = true;

// Show claims info box (orange ID box with extracted claims)
if (data.claims && data.claims.length > 0) {
    showClaimsInfoBox(cardId, data.claims, data.summary.total_claims);
}

// Update progress indicator with completion message
const total = data.summary.total_claims;
const withRefs = data.summary.claims_with_references;
const withoutRefs = data.summary.claims_without_references;

let claimSummary;
if (withoutRefs === 0) {
    claimSummary = `${total} claim${total !== 1 ? 's' : ''} (all referenced)`;
} else if (withRefs === 0) {
    claimSummary = `${total} claim${total !== 1 ? 's' : ''} (none referenced)`;
} else {
    claimSummary = `${total} claim${total !== 1 ? 's' : ''} (${withRefs} referenced, ${withoutRefs} not)`;
}

// Update thinking indicator to show extraction complete with summary
updateThinkingInCard(cardId, `Extraction complete! Found ${claimSummary}.`);

// Complete thinking indicator immediately
setTimeout(() => {
    completeThinkingInCard(cardId, `Extraction complete! Found ${claimSummary}.`);

    // Wait 1 second, then open preview
    setTimeout(() => {
        globalState.activePreviewCard = null;
        createPreviewCard();
    }, 1000);
}, 300);
        }

        // Handle reference check error
        function handleReferenceCheckError(data, cardId) {
// Use cardId from referenceCheckState if not provided
if (!cardId) {
    cardId = referenceCheckState.cardId;
}
if (!cardId) return;

// Complete thinking with error
completeThinkingInCard(cardId, 'Reference check failed');

// Show error message
const errorMessage = data.error || data.message || 'An error occurred during reference checking';
showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');

// Re-enable textarea if input container exists
const input = document.getElementById(`${cardId}-input`);
if (input && referenceCheckState.submittedText) {
    input.value = referenceCheckState.submittedText;
    input.rows = 12;
    input.disabled = false;
    input.style.cursor = 'text';
}
        }

        // ========== UPLOAD INTERVIEW HANDLERS ==========

        async function handleUploadInterviewUpdate(data) {
console.log('[UPLOAD_INTERVIEW] Received update:', data);

const conversationId = data.conversation_id;
if (!conversationId) return;

// Find the interview card
const cardId = globalState.uploadInterviewCardId;
if (!cardId) return;

const chatContainer = document.getElementById(`${cardId}-chat`);
const inputContainer = document.getElementById(`${cardId}-input-container`);

if (!chatContainer) return;

// Add AI message to conversation using existing chat function
await addChatMessage(cardId, 'ai', data.ai_message);

if (data.mode === 1) {
    // Mode 1: AI is asking questions
    if (inputContainer) inputContainer.style.display = 'block';

    // Use createButtonRow in card's standard buttons container
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Submit',
            variant: 'primary',
            width: 'full',
            callback: async (e) => {
                const button = e.target.closest('button');
                const userMessage = document.getElementById(`${cardId}-input`).value;
                if (userMessage.trim()) {
                    markButtonSelected(button, 'Thinking...');
                    await addChatMessage(cardId, 'user', userMessage);
                    sendInterviewMessage(conversationId, userMessage);
                    document.getElementById(`${cardId}-input`).value = '';
                }
            }
        }
    ]);

} else if (data.mode === 2) {
    // Mode 2: AI showing understanding, requesting confirmation

    // Store confirmation response for later use
    window[`${cardId}_confirmation`] = data.confirmation_response;

    if (inputContainer) inputContainer.style.display = 'block';

    // Update placeholder to indicate blank = confirm (like table maker)
    const input = document.getElementById(`${cardId}-input`);
    if (input) {
        input.placeholder = 'Confirm or ask for changes (blank to confirm)...';
        input.value = '';
        input.focus();
    }

    // Single Submit button - blank/affirmatives trigger immediate confirmation
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Submit',
            variant: 'primary',
            width: 'full',
            callback: async (e) => {
                const button = e.target.closest('button');
                const userMessage = document.getElementById(`${cardId}-input`).value.trim();

                // Check if this is a simple confirmation (blank, "yes", "looks good", etc.)
                const isSimpleConfirmation = !userMessage ||
                    /^(yes|yeah|yep|yup|sure|ok|okay|good|great|perfect|sounds good|looks good|go|go for it|start|proceed|confirm)\.?$/i.test(userMessage);

                const confirmation = window[`${cardId}_confirmation`];

                if (isSimpleConfirmation && confirmation) {
                    // Use pre-generated confirmation - skip a round trip
                    markButtonSelected(button, 'Generating...');

                    // Show user confirmation
                    const displayMessage = userMessage || '✓ Confirmed';
                    await addChatMessage(cardId, 'user', displayMessage);

                    // Show AI confirmation message
                    await addChatMessage(cardId, 'ai', confirmation.ai_message);

                    // Hide input and show thinking
                    if (inputContainer) inputContainer.style.display = 'none';
                    showThinkingInCard(cardId, 'Starting configuration generation...');

                    // Clear confirmation (used once)
                    window[`${cardId}_confirmation`] = null;

                    // Send empty message to trigger config generation
                    await sendInterviewMessage(conversationId, '');
                } else {
                    // User wants changes - send their message
                    markButtonSelected(button, 'Thinking...');
                    await addChatMessage(cardId, 'user', userMessage);
                    sendInterviewMessage(conversationId, userMessage);
                    document.getElementById(`${cardId}-input`).value = '';
                }
            }
        }
    ]);

} else if (data.mode === 3) {
    // Mode 3: Config generation starting
    if (inputContainer) inputContainer.style.display = 'none';
    await addChatMessage(cardId, 'ai', data.ai_message);
    showThinkingInCard(cardId, 'Generating configuration...');
}
        }

        async function handleConfigGenerationStart(data) {
console.log('[UPLOAD_INTERVIEW] Config generation starting');

const cardId = globalState.uploadInterviewCardId;
if (!cardId) return;

// Update progress message
updateThinkingProgress(cardId, 0, data.message || 'Generating validation configuration...');
        }

        // Handle config generation completion for upload interview - auto-proceeds to preview
        // Note: config_generation_progress is handled by websocket.js routeMessage, not here
        async function handleUploadInterviewConfigComplete(data, cardId) {
if (data.type === 'config_generation_complete') {
    console.log('[UPLOAD_INTERVIEW] Config generation complete, proceeding to preview');
    completeThinkingInCard(cardId, 'Configuration generated!');

    globalState.currentConfig = data;
    globalState.excelFileUploaded = true;
    globalState.configValidated = true;
    globalState.configStored = true;

    // Save clarifying questions for later use in refinement
    if (data.clarifying_questions) {
        globalState.savedQuestions = data.clarifying_questions;
    }

    let aiMessage = data.ai_summary || data.ai_response || 'Configuration generated successfully!';
    await addChatMessage(cardId, 'ai', aiMessage);

    // Auto-proceed to preview after brief delay
    setTimeout(() => {
        globalState.activePreviewCard = null;
        createPreviewCard();
    }, 1000);

} else if (data.type === 'config_generation_failed' || data.error || data.type === 'error') {
    completeThinkingInCard(cardId, 'Generation failed');
    const errorMessage = data.error || data.message || 'Configuration generation failed';
    showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');
}
        }

        async function handleUploadInterviewError(data) {
console.error('[UPLOAD_INTERVIEW] Error:', data.error);

const cardId = globalState.uploadInterviewCardId;
if (!cardId) return;

// Show error in chat
await addChatMessage(cardId, 'ai', `❌ **Error:** ${data.error}`);

// Complete thinking with error
completeThinkingInCard(cardId, 'Interview failed');
        }

        async function createUploadInterviewCard(previousCardId, uploadData) {
// Hide or complete previous card
if (previousCardId) {
    showFinalCardState(previousCardId, 'Starting upload interview...', 'success');
}

const cardId = generateCardId();
globalState.uploadInterviewCardId = cardId;

const content = `
    <div id="${cardId}-messages"></div>
    <div id="${cardId}-chat" class="chat-container"></div>
    <div id="${cardId}-input-container" style="display: none; margin-top: 16px;">
        <textarea id="${cardId}-input" class="table-maker-textarea"
            placeholder="Type your response..."
            style="width: 100%; min-height: 80px; resize: vertical;"
            onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();const btn=document.querySelector('#${cardId}-buttons button.primary');if(btn){btn.focus();btn.classList.add('hover');setTimeout(()=>btn.classList.remove('hover'),1500);}}"></textarea>
    </div>
`;

const card = createCard({
    id: cardId,
    icon: '📊',
    title: 'Table Upload Configuration',
    subtitle: 'Analyzing your table structure',
    content: content
});

// Show thinking indicator immediately with initial message
showThinkingInCard(cardId, 'Analyzing your table...', true);

// Register card handler for config generation completion only
// Progress messages are handled by websocket.js routeMessage
registerCardHandler(cardId, ['config_generation_complete'],
    (data) => handleUploadInterviewConfigComplete(data, cardId));

// Start the interview (use isStart=true for first message)
await sendInterviewMessage(uploadData.conversation_id, '', true);
        }

        async function sendInterviewMessage(conversationId, userMessage, isStart = false) {
const sessionId = conversationId.replace('upload_interview_', '');

try {
    const response = await fetch(`${API_BASE}/validate`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: isStart ? 'startUploadInterview' : 'continueUploadInterview',
            session_id: sessionId,
            conversation_id: conversationId,
            user_message: userMessage,
            email: globalState.email
        })
    });

    const data = await response.json();

    if (!data.success) {
        console.error('[UPLOAD_INTERVIEW] Failed to send message:', data.error);
        alert(`Failed to send message: ${data.error}`);
    }
} catch (error) {
    console.error('[UPLOAD_INTERVIEW] Error sending message:', error);
    alert(`Error: ${error.message}`);
}
        }

        function createInterviewButton(text, variant, onClick) {
const button = document.createElement('button');
button.textContent = text;
button.className = `btn btn-${variant}`;
button.onclick = onClick;
return button;
        }

        // Helper function to trigger preview validation
        function triggerPreviewValidation(cardId) {
// Starting preview validation

// First, add download button for unvalidated table
const messagesDiv = document.getElementById(`${cardId}-messages`);
if (messagesDiv) {
    const downloadButtonHtml = `
        <div style="margin: 1rem 0;">
            <button class="std-button tertiary" id="${cardId}-download-table-btn" style="width: 100%;" disabled>
                <span class="button-text">📥 Preparing Download...</span>
            </button>
        </div>
    `;
    messagesDiv.insertAdjacentHTML('beforeend', downloadButtonHtml);

    // Enable download button after 3 seconds
    setTimeout(() => {
        const downloadBtn = document.getElementById(`${cardId}-download-table-btn`);
        if (downloadBtn) {
            downloadBtn.disabled = false;
            downloadBtn.querySelector('.button-text').textContent = '📥 Download Unvalidated Table';
            downloadBtn.addEventListener('click', downloadUnvalidatedTable);
        }
    }, 3000); // 3 second delay for download to be ready
}

// Update card for validation phase
const cardTitle = document.querySelector(`#${cardId} .card-title`);
if (cardTitle) cardTitle.textContent = 'Validating Table Preview';

const cardSubtitle = document.querySelector(`#${cardId} .card-subtitle`);
if (cardSubtitle) cardSubtitle.textContent = 'Running validation on first 3 rows...';

showThinkingInCard(cardId, 'Validating table preview...', true);

// Register handler for preview progress updates
unregisterCardHandler(cardId);
registerCardHandler(cardId, ['preview_progress', 'progress_update'], (wsData, handlerCardId) => {
    // Progress updates are handled by global routing
    // This registration ensures the card receives preview validation updates
});

// Trigger preview validation via existing flow
// This will use the uploaded Excel file and trigger validation
fetch(`${API_BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        action: 'processExcel',
        email: globalState.email,
        session_id: globalState.sessionId,
        preview_first_row: 'true',
        async: 'true'
    })
}).then(response => response.json())
  .then(data => {
      if (data.status === 'processing') {
          // Preview validation queued
          // WebSocket updates will handle the progress
      } else if (data.error) {
          completeThinkingInCard(cardId, 'Validation failed');
          showMessage(`${cardId}-messages`, `Validation error: ${data.error}`, 'error');
      }
  })
  .catch(error => {
      console.error('Error starting preview validation:', error);
      completeThinkingInCard(cardId, 'Validation failed');
      showMessage(`${cardId}-messages`, 'Failed to start validation. Please try again.', 'error');
  });
        }
