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

    const card = createCard({
        id: cardId,
        icon: '🚀',
        title: 'Get Started',
        subtitle: 'Choose your own adventure!',
        content,
        buttons: [
            {
                text: '✨ Create Table from Prompt',
                icon: '',
                variant: 'primary',
                callback: async function() {
                    proceedWithTableMaker(cardId);
                }
            },
            {
                text: '📁 Upload Your Own Table',
                icon: '',
                variant: 'secondary',
                callback: async function() {
                    proceedWithUpload(cardId);
                }
            },
            {
                text: '🎯 Explore a Demo Table',
                icon: '',
                variant: 'tertiary',
                callback: async function() {
                    proceedWithDemo(cardId);
                }
            },
            {
                text: '🔍 Check Text References',
                icon: '',
                variant: 'quaternary',
                callback: async function() {
                    proceedWithReferenceCheck(cardId);
                }
            }
        ]
    });

    return card;
}

function proceedWithTableMaker(cardId) {
    // Show completion state
    showFinalCardState(cardId, 'Starting table maker...', 'success');

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

                            // Go directly to configuration
                            setTimeout(() => {
                                createConfigurationCard();
                            }, 1000);
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
        await uploadExcelFile(cardId, file);
        // Create configuration card after successful upload
        setTimeout(() => {
            createConfigurationCard();
        }, 500);
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

            return; // Don't proceed to normal config flow
        }

        // Show upload completion
        showMessage(`${cardId}-messages`,
            `File uploaded: ${file.name}`,
            'success'
        );

        // Show clean success state
        showFinalCardState(cardId,
            `${file.name} uploaded and analyzed`,
            'success'
        );

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
