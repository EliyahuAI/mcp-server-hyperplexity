/* ========================================
 * 06-upload.js - File Upload & S3
 *
 * Handles file uploads, S3 presigned URLs,
 * drag-drop functionality, and file validation.
 *
 * Dependencies: 00-config.js, 04-cards.js, 05-chat.js
 * ======================================== */

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function createUploadOrDemoCard() {
    const cardId = generateCardId();
    const content = `
        <div id="${cardId}-options" style="text-align: center;">
        </div>
        <div id="${cardId}-messages"></div>
        <div id="${cardId}-buttons"></div>
    `;

    // Base buttons available in all environments
    const baseButtons = [
        {
            text: '✨ Create Table from Prompt',
            icon: '',
            variant: 'primary',
            callback: async function() {
                if (DEFER_EMAIL_VALIDATION) {
                    requireEmailThen(() => proceedWithTableMaker(cardId), 'create your table');
                } else {
                    proceedWithTableMaker(cardId);
                }
            }
        },
        {
            text: '📁 Upload Your Own Table',
            icon: '',
            variant: 'secondary',
            callback: async function() {
                if (DEFER_EMAIL_VALIDATION) {
                    requireEmailThen(() => proceedWithUpload(cardId), 'upload your table');
                } else {
                    proceedWithUpload(cardId);
                }
            }
        }
    ];

    // Dev-only buttons
    const devButtons = [
        {
            text: '🎯 Explore a Demo Table',
            icon: '',
            variant: 'tertiary',
            callback: async function() {
                if (DEFER_EMAIL_VALIDATION) {
                    requireEmailThen(() => proceedWithDemo(cardId), 'explore the demo');
                } else {
                    proceedWithDemo(cardId);
                }
            }
        },
        {
            text: '🔍 Check Text References',
            icon: '',
            variant: 'quaternary',
            callback: async function() {
                if (DEFER_EMAIL_VALIDATION) {
                    requireEmailThen(() => proceedWithReferenceCheck(cardId), 'check your references');
                } else {
                    proceedWithReferenceCheck(cardId);
                }
            }
        }
    ];

    // Only include dev buttons in dev environment
    const allButtons = CURRENT_ENV === 'dev' ? [...baseButtons, ...devButtons] : baseButtons;

    const card = createCard({
        id: cardId,
        icon: '🚀',
        title: 'Get Started',
        subtitle: 'Choose your own adventure!',
        content,
        buttons: allButtons
    });

    return card;
}

function proceedWithTableMaker(cardId) {
    // Show completion state
    showFinalCardState(cardId, 'Starting table maker...', 'success');

    // EARLY WARMUP: Start lambda warmup and session initialization IMMEDIATELY
    // This runs in parallel while we show the card, so by the time user submits,
    // the lambda is warm and WebSocket is connected
    if (typeof preInitializeTableMaker === 'function') {
        preInitializeTableMaker();
    }

    // Create table maker card
    setTimeout(() => {
        createTableMakerCard();
    }, 500);
}

function proceedWithReferenceCheck(cardId) {
    // Show completion state
    showFinalCardState(cardId, 'Starting reference check...', 'success');

    // Create reference check card
    setTimeout(() => {
        createReferenceCheckCard();
    }, 500);
}

function proceedWithDemo(cardId) {
    // Show completion state - only green success box
    showFinalCardState(cardId, 'Loading demo selection...', 'success');

    // Create demo selection card
    setTimeout(() => createSelectDemoCard(), 500);
}

function proceedWithUpload(cardId) {
    // Show completion state
    showFinalCardState(cardId, 'Ready to select your file...', 'success');

    // Directly open file picker instead of creating another card
    setTimeout(() => {
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.xlsx,.xls,.csv';
        fileInput.style.display = 'none';

        fileInput.onchange = (e) => {
            if (e.target.files && e.target.files[0]) {
                // Store the selected file globally
                globalState.excelFile = e.target.files[0];
                globalState.excelFileName = e.target.files[0].name;

                // Show uploading progress immediately
                showFinalCardState(cardId, `Uploading file: ${e.target.files[0].name}`, 'info');

                // Skip upload card entirely - upload file then go to config
                setTimeout(async () => {
                    try {

                        // Upload the file directly (same as handleFileSelect does)
                        const formData = new FormData();
                        formData.append('excel_file', globalState.excelFile);
                        formData.append('email', globalState.email);
                        formData.append('action', 'processExcel');
                        // New file upload should NEVER reuse existing session - always generate new session ID

                        const uploadResponse = await fetch(`${API_BASE}/upload`, {
                            method: 'POST',
                            body: formData
                        });

                        const data = await uploadResponse.json();

                        if (uploadResponse.ok && data.success) {
                            // Show upload completion
                            showFinalCardState(cardId, `File uploaded: ${globalState.excelFileName}`, 'success');
                            // Update session info from upload
                            if (data.session_id) {
                                globalState.sessionId = data.session_id;
                                localStorage.setItem('sessionId', data.session_id);
                            }
                            globalState.excelFileUploaded = true;
                            globalState.workflowPhase = 'upload';

                            // [FIX] Store matching configs if found
                            if (data.matching_configs && data.matching_configs.success && data.matching_configs.matches) {
                                globalState.matchingConfigs = data.matching_configs;
                            } else {
                                globalState.matchingConfigs = null;
                            }

                            // Update completion message to show upload success
                            showFinalCardState(cardId, `File uploaded: ${globalState.excelFileName}`, 'success');

                            // Check if we should start upload interview
                            if (data.action === 'start_interview' && data.conversation_id) {
                                console.log('[UPLOAD_INTERVIEW] Starting interview (FormData path) for', data.conversation_id);

                                // Store conversation info
                                globalState.uploadInterviewConversationId = data.conversation_id;
                                globalState.tableAnalysis = data.table_analysis;

                                // Show interview UI instead of going to config
                                setTimeout(() => {
                                    createUploadInterviewCard(cardId, data);
                                }, 500);
                            } else {
                                // Go directly to configuration (old flow)
                                setTimeout(() => {
                                    createConfigurationCard();
                                }, 1000);
                            }
                        } else {
                            throw new Error(data.error || 'Failed to upload file');
                        }
                    } catch (error) {
                        console.error('Upload error:', error);
                        showFinalCardState(cardId, `Upload failed: ${error.message}`, 'error');
                    }
                }, 1000);
            }
        };

        // Add to body and trigger click
        document.body.appendChild(fileInput);
        fileInput.click();
        document.body.removeChild(fileInput);
    }, 500);
}

// 2. File Upload Card
function createUploadCard() {
    const cardId = generateCardId();
    const content = `
        <div class="drop-zone" id="${cardId}-dropzone">
            <div class="drop-zone-icon">📊</div>
            <div class="drop-zone-text">
                <p><strong>Drop Excel/CSV file here</strong></p>
                <p>or click to browse</p>
            </div>
            <input type="file" id="${cardId}-file" class="file-input"
                accept=".xlsx,.xls,.csv">
            <div id="${cardId}-file-info" class="file-info" style="display: none;">
                <div class="file-info-name"></div>
                <div class="file-info-size"></div>
            </div>
        </div>
        <div id="${cardId}-messages"></div>
        <div id="${cardId}-options"></div>
    `;

    const card = createCard({
        id: cardId,  // Pass explicit ID
        icon: '📁',
        title: 'Upload Table',
        subtitle: 'Select your Excel or CSV file <span class="info-icon" onclick="showUploadInfo()" title="Requirements Info">ℹ️</span>',
        content
    });

    // Setup file handling
    setupFileUpload(cardId);

    return card;
}

function setupFileUpload(cardId) {
    const dropZone = document.getElementById(`${cardId}-dropzone`);
    const fileInput = document.getElementById(`${cardId}-file`);

    // Click to browse
    dropZone.onclick = () => fileInput.click();

    // File selection
    fileInput.onchange = (e) => handleFileSelect(e, cardId);

    // Drag and drop
    dropZone.ondragover = (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    };

    dropZone.ondragleave = () => {
        dropZone.classList.remove('drag-over');
    };

    dropZone.ondrop = (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect({ target: fileInput }, cardId);
        }
    };
}

// Validate Excel file before processing
function validateExcelFile(file) {
    // Check file size (100MB limit)
    const maxSize = 100 * 1024 * 1024; // 100MB
    if (file.size > maxSize) {
        return { valid: false, error: 'File too large. Maximum size is 100MB.' };
    }

    // Check file type
    const allowedTypes = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
        'application/vnd.ms-excel', // .xls
        'text/csv', // .csv
        'application/csv'
    ];

    const allowedExtensions = ['.xlsx', '.xls', '.csv'];
    const fileName = file.name.toLowerCase();
    const hasValidExtension = allowedExtensions.some(ext => fileName.endsWith(ext));

    if (!allowedTypes.includes(file.type) && !hasValidExtension) {
        return {
            valid: false,
            error: 'Invalid file type. Please upload Excel (.xlsx, .xls) or CSV files only.'
        };
    }

    // Basic file name validation
    if (fileName.length > 255) {
        return { valid: false, error: 'File name too long.' };
    }

    return { valid: true };
}

// Validate config file before processing
function validateConfigFile(file) {
    // Check file size (10MB limit for config files)
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
        return { valid: false, error: 'Config file too large. Maximum size is 10MB.' };
    }

    // Check file type
    if (file.type !== 'application/json' && !file.name.toLowerCase().endsWith('.json')) {
        return { valid: false, error: 'Invalid file type. Please upload JSON files only.' };
    }

    // Check if file is not empty
    if (file.size === 0) {
        return { valid: false, error: 'Config file is empty.' };
    }

    return { valid: true };
}

async function handleFileSelect(event, cardId) {
    const file = event.target.files[0];
    if (!file) {
        return;
    }

    // Validate file before processing
    const validation = validateExcelFile(file);
    if (!validation.valid) {
        showMessage(`${cardId}-messages`, `File validation failed: ${validation.error}`, 'error');
        // Reset file input
        event.target.value = '';
        return;
    }

    // Only clear session data after successful validation
    globalState.sessionId = null;
    globalState.excelFileUploaded = false;
    globalState.configStored = false;
    globalState.configValidated = false;
    localStorage.removeItem('sessionId');

    // Store file reference
    globalState.excelFile = file;

    // Hide the entire drop zone
    const dropZone = document.getElementById(`${cardId}-dropzone`);
    if (dropZone) {
        dropZone.style.display = 'none';
    }

    // Show processing message while uploading
    showMessage(`${cardId}-messages`,
        `Uploading file: ${file.name}`,
        'info'
    );

    // Immediately upload Excel file to establish session
    try {
        const interviewTriggered = await uploadExcelFile(cardId, file);

        // Only create configuration card if upload interview was NOT triggered
        if (!interviewTriggered) {
            setTimeout(() => {
                createConfigurationCard();
            }, 500);
        }
    } catch (error) {
        // Reset UI on failure
        dropZone.style.pointerEvents = 'auto';
        dropZone.style.opacity = '1';
        fileInfoEl.style.display = 'none';
    }
}

async function uploadExcelFile(cardId, file) {
    try {
        // Validate file size (50MB max - no longer limited by API Gateway!)
        const maxSize = 50 * 1024 * 1024;
        if (file.size > maxSize) {
            throw new Error(`File too large. Maximum size is ${maxSize / 1024 / 1024}MB`);
        }

        // Step 1: Request presigned URL from backend
        const presignedResponse = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'requestPresignedUrl',
                file_type: 'excel',
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

        // Store upload info
        const uploadId = presignedData.upload_id;
        const s3Key = presignedData.s3_key;
        const sessionId = presignedData.session_id;

        // Store session_id if backend generated one
        if (sessionId && !globalState.sessionId) {
            globalState.sessionId = sessionId;
            localStorage.setItem('sessionId', sessionId);
        }

        showMessage(`${cardId}-messages`,
            `Uploading ${file.name} to secure storage...`,
            'info'
        );

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
                'x-amz-meta-file_type': 'excel',
                'x-amz-meta-file_size': file.size.toString(),
                'x-amz-meta-uploaded_at': new Date().toISOString()
            }
        });

        if (!uploadResponse.ok) {
            throw new Error(`Upload failed with status ${uploadResponse.status}`);
        }

        console.log('[EXCEL_UPLOAD] File uploaded to S3 successfully');

        // Step 3: Confirm upload complete (no processing yet - just confirmation)
        const confirmResponse = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'confirmUploadComplete',
                upload_id: uploadId,
                s3_key: s3Key,
                session_id: sessionId,
                file_type: 'excel',
                filename: file.name,
                email: globalState.email
            })
        });

        const confirmData = await confirmResponse.json();

        if (!confirmResponse.ok || !confirmData.success) {
            throw new Error(confirmData.message || 'Failed to confirm upload');
        }

        // Store file info in globalState for later processing
        globalState.excelFileUploaded = true;
        globalState.excelS3Key = s3Key;
        globalState.excelFilename = file.name;
        globalState.storagePath = confirmData.storage_path;

        // Store matching configs if found
        if (confirmData.matching_configs && confirmData.matching_configs.success && confirmData.matching_configs.matches) {
            globalState.matchingConfigs = confirmData.matching_configs;
        } else {
            globalState.matchingConfigs = null;
        }

        // Check if we should start upload interview
        if (confirmData.action === 'start_interview' && confirmData.conversation_id) {
            console.log('[UPLOAD_INTERVIEW] Starting interview for', confirmData.conversation_id);

            // Store conversation info
            globalState.uploadInterviewConversationId = confirmData.conversation_id;
            globalState.tableAnalysis = confirmData.table_analysis;

            // Show interview UI instead of going to config
            setTimeout(() => {
                createUploadInterviewCard(cardId, confirmData);
            }, 500);

            return true; // Interview triggered - signal to caller
        }

        // Check if a matching config was found - go directly to config card
        if (confirmData.action === 'use_matching_config' && globalState.matchingConfigs) {
            console.log('[MATCHING_CONFIG] Found matching config, skipping interview');

            // Show success with match info
            showFinalCardState(cardId,
                `${file.name} uploaded - matching configuration found!`,
                'success'
            );

            // Go directly to configuration card where user can use the match
            setTimeout(() => {
                createConfigurationCard();
            }, 500);

            return true; // Config flow handled - signal to caller
        }

        // Show upload completion (fallback for legacy flow)
        showMessage(`${cardId}-messages`,
            `File uploaded: ${file.name}`,
            'success'
        );

        // Show clean success state
        showFinalCardState(cardId,
            `${file.name} uploaded and analyzed`,
            'success'
        );

        return false; // Interview not triggered - caller should create config card

    } catch (error) {
        throw error;
    }
}

async function handleConfigUpload(event, cardId) {
    const file = event.target.files[0];
    if (!file) {
        return;
    }

    // Validate config file before processing
    const validation = validateConfigFile(file);
    if (!validation.valid) {
        showMessage(`${cardId}-messages`, `Config file validation failed: ${validation.error}`, 'error');
        // Reset file input
        event.target.value = '';
        return;
    }

    globalState.configFile = file;

    // Hide all card content and show processing
    const messagesContainer = document.getElementById(`${cardId}-messages`);
    const optionsContainer = document.getElementById(`${cardId}-options`);
    const buttonsContainer = document.getElementById(`${cardId}-buttons`);
    const matchingInfoContainer = document.getElementById(`${cardId}-matching-info`);

    if (optionsContainer) optionsContainer.style.display = 'none';
    if (buttonsContainer) buttonsContainer.style.display = 'none';
    if (matchingInfoContainer) matchingInfoContainer.style.display = 'none';

    // Show thinking indicators
    showThinkingInCard(cardId, 'Validating configuration file...');
    // Progress routed to card level;

    try {
        // Read and parse file locally first
        const configText = await file.text();
        const config = JSON.parse(configText);

        // Validate config structure locally first
        if (!config || !config.validation_targets || !Array.isArray(config.validation_targets)) {
            throw new Error('Invalid config structure. Must have validation_targets array.');
        }

        // Config validation only - Excel file already uploaded and session established
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'validateConfig',
                config: config,
                is_upload: true,
                email: globalState.email,
                session_id: globalState.sessionId
            })
        });

        const data = await response.json();

        if (response.ok && data.valid) {
            completeThinkingInCard(cardId, 'Configuration validated!');
            // Progress routed to card level;

            globalState.configValidated = true;
            globalState.configStored = true;

            // Show success with filename and validation status
            showFinalCardState(cardId,
                `${file.name} uploaded and validated successfully`,
                'success'
            );

            // Auto-proceed to preview
            setTimeout(() => createPreviewCard(), 1000);
        } else {
            completeThinkingInCard(cardId, 'Validation failed');
            // Progress routed to card level;

            // Show error message
            if (messagesContainer) {
                messagesContainer.innerHTML = `
                    <div class="message message-error" style="margin-bottom: 1rem;">
                        <span class="message-icon"></span>
                        <span>Configuration validation failed: ${data.message || 'Unknown error'}</span>
                    </div>
                `;
            }

            // Offer repair options
            offerConfigRepair(cardId, data.message || 'Unknown error', config);
        }
    } catch (error) {
        completeThinkingInCard(cardId, 'Upload failed');
        // Progress routed to card level;

        console.error('Config validation error:', error);

        // Show error message
        if (messagesContainer) {
            messagesContainer.innerHTML = `
                <div class="message message-error" style="margin-bottom: 1rem;">
                    <span class="message-icon"></span>
                    <span>Error reading config: ${error.message}</span>
                </div>
            `;
        }
    }
}
function createSelectDemoCard() {
    const cardId = generateCardId();
    const content = `
<div id="${cardId}-options" style="text-align: center; padding: 20px;">
    <div id="${cardId}-demos-list" style="display: flex; flex-direction: column; gap: 12px;">
        <div style="text-align: center; color: var(--text-secondary);">
            <span>Loading available demos...</span>
        </div>
    </div>
</div>
<div id="${cardId}-messages"></div>
    `;

    const card = createCard({
id: cardId,
icon: '🎯',
title: 'Select Demo Table',
subtitle: 'Choose from pre-configured examples',
content
    });

    // Load available demos
    loadAvailableDemos(cardId);

    return card;
}

async function loadAvailableDemos(cardId) {
    try {
const response = await fetch(`${API_BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        action: 'listDemos'
    })
});

const result = await response.json();

if (!result.success) {
    throw new Error(result.error || 'Failed to load demos');
}

const demosList = document.getElementById(`${cardId}-demos-list`);
if (!demosList) return;

if (!result.demos || result.demos.length === 0) {
    demosList.innerHTML = `
        <div style="text-align: center; color: #666; padding: 20px;">
            <p>No demos available at this time.</p>
            <p>Please upload your own table file.</p>
        </div>
    `;
    return;
}

// Create demo buttons with cycling colors (last button always green)
const colorCycle = ['primary', 'secondary', 'tertiary', 'quaternary', 'quinary'];
const demosHtml = result.demos.map((demo, index) => {
    // Calculate position from the end so last demo is always green
    const positionFromEnd = result.demos.length - 1 - index;
    const colorIndex = positionFromEnd % 5;
    return `
    <button class="std-button ${colorCycle[colorIndex]}" style="width: 100%; text-align: left; padding: 16px;"
            onclick="selectDemo('${cardId}', '${demo.name}', this)">
        <div style="display: flex; flex-direction: column; gap: 4px; text-align: left; align-items: flex-start; width: 100%;">
            <div style="font-weight: bold; font-size: var(--font-size-base); text-align: left; width: 100%;">
                ${demo.display_name}
            </div>
            <div style="font-size: var(--font-size-small); color: var(--text-secondary); font-weight: normal; text-align: left; width: 100%;">
                ${demo.description.length > 100 ?
                    demo.description.substring(0, 100) + '...' :
                    demo.description}
            </div>
        </div>
    </button>
    `;
}).join('');

demosList.innerHTML = demosHtml;

    } catch (error) {
console.error('Error loading demos:', error);
const demosList = document.getElementById(`${cardId}-demos-list`);
if (demosList) {
    demosList.innerHTML = `
        <div style="text-align: center; color: #d32f2f; padding: 20px;">
            <p>Failed to load demos: ${error.message}</p>
            <button class="std-button secondary" onclick="loadAvailableDemos('${cardId}')">
                🔄 Try Again
            </button>
        </div>
    `;
}
    }
}

async function selectDemo(cardId, demoName, buttonElement) {
    markButtonSelected(buttonElement, '🚀 Loading Demo...');

    try {
// Make sure we have email (sessionId will be created/updated by backend)
if (!globalState.email) {
    // Try to get email from sessionStorage if not in globalState
    const storedEmail = sessionStorage.getItem('validatedEmail');
    if (storedEmail && storedEmail.includes('@')) {
        globalState.email = storedEmail;
    } else {
        throw new Error('Email not provided - please enter your email first');
    }
}

const requestBody = {
    action: 'selectDemo',
    demo_name: demoName,
    email: globalState.email
};

// Only include session_id if we actually have one (not null/undefined/empty)
if (globalState.sessionId) {
    requestBody.session_id = globalState.sessionId;
}


const response = await fetch(`${API_BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody)
});

const result = await response.json();

if (!result.success) {
    // Check if it's a session-related error
    const errorMsg = result.error || 'Failed to load demo';

    // Only clear session data for actual session errors, not other backend errors
    if (errorMsg.toLowerCase().includes('session') && (errorMsg.toLowerCase().includes('expired') || errorMsg.toLowerCase().includes('invalid'))) {
        // Clear stale session data
        localStorage.removeItem('sessionId');
        sessionStorage.removeItem('validatedEmail');
        globalState.sessionId = null;
        globalState.email = '';
        throw new Error('Session expired - please refresh the page');
    }
    throw new Error(errorMsg);
}

// Update session ID with new one from demo (like table uploads)
if (result.session_id) {
    globalState.sessionId = result.session_id;
    // Store new session ID in localStorage for persistence
    localStorage.setItem('sessionId', result.session_id);
}

// Set global state as if user uploaded files
globalState.excelFileUploaded = true;
globalState.configStored = true;
globalState.currentConfig = result.config_data;

// Show success message with demo details
const successMessage = `
    <div style="text-align: left;">
        <div style="font-weight: bold; margin-bottom: 8px; font-size: var(--font-size-base);">
            ${result.demo.display_name}
        </div>
        <div style="color: var(--text-secondary); line-height: 1.4; font-size: var(--font-size-base);">
            ${result.demo.description}
        </div>
    </div>
`;

showFinalCardState(cardId, successMessage, 'success');

// Auto-proceed to preview after short delay
setTimeout(() => {
    createPreviewCard();
}, 1500);

    } catch (error) {
console.error('Error selecting demo:', error);
markButtonUnselected(buttonElement, buttonElement.innerHTML);
showMessage(`${cardId}-messages`, `Failed to load demo: ${error.message}`, 'error');
    }
}

// Make demo functions globally available for onclick handlers
window.proceedWithDemo = proceedWithDemo;
window.proceedWithUpload = proceedWithUpload;
window.selectDemo = selectDemo;
window.loadAvailableDemos = loadAvailableDemos;

// ============================================

// selectUploadConfig function removed - now handled inline in button callback

async function selectRecentConfig(cardId, button) {
    markButtonSelected(button, '🔄 Searching for Recent Configs...');
    
    try {
// Search for matching configs
const response = await fetch(`${API_BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        action: 'findMatchingConfig',
        email: globalState.email,
        session_id: globalState.sessionId || '',
        limit: 5
    })
});

const result = await response.json();


if (!result.success) {
    throw new Error(result.error || 'Failed to search for matching configs');
}

// Filter for good matches (>= 80% - backend already does this but double-check)
const goodMatches = result.matches ? result.matches.filter(match => match.match_score >= 0.8) : [];

if (goodMatches && goodMatches.length > 0) {
    await showRecentConfigOptions(cardId, goodMatches, result.table_columns);
} else {
    const totalFound = result.matches ? result.matches.length : 0;
    const message = totalFound > 0 ?
                  `Found ${totalFound} previous configs but none match well enough (need ≥80% match). Use a <strong>Configuration ID</strong> from your email, upload a config file, or create one with AI.` :
                  'No matching configurations found from your previous sessions. Use a <strong>Configuration ID</strong> from your email, upload a config file, or create one with AI.';

    showMessage(`${cardId}-messages`, message, 'info');
    // Reset button
    markButtonUnselected(button);
}

    } catch (error) {
console.error('Error finding recent configs:', error);
showMessage(`${cardId}-messages`, `Error searching for recent configs: ${error.message}`, 'error');
markButtonUnselected(button);
    }
}

async function selectRecentConfigFromStored(cardId, button) {
    markButtonSelected(button, '🔄 Loading Recent Configs...');
    
    try {
// Use already-found matching configs from upload (only show good matches)
const goodMatches = globalState.matchingConfigs && 
                   globalState.matchingConfigs.matches &&
                   globalState.matchingConfigs.matches.filter(match => match.match_score >= 0.8);

if (goodMatches && goodMatches.length > 0) {
    await showRecentConfigOptions(cardId, goodMatches, globalState.matchingConfigs.table_columns);
} else {
    const totalMatches = (globalState.matchingConfigs && globalState.matchingConfigs.matches) ?
                       globalState.matchingConfigs.matches.length : 0;
    const message = totalMatches > 0 ?
                   `Found ${totalMatches} previous configs but none match well enough (need ≥80% match). Use a <strong>Configuration ID</strong> from your email, upload a config file, or create one with AI.` :
                   'No matching configurations available. Use a <strong>Configuration ID</strong> from your email, upload a config file, or create one with AI.';

    showMessage(`${cardId}-messages`, message, 'info');
    // Reset button
    markButtonUnselected(button);
}

    } catch (error) {
        console.error('Error displaying stored recent configs:', error);
        showMessage(`${cardId}-messages`, `Error displaying recent configs: ${error.message}`, 'error');
        markButtonUnselected(button);
    }
}