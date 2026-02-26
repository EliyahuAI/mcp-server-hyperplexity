/* ========================================
 * 08-config-generation.js - Config Generation & Refinement
 *
 * Handles configuration generation, refinement,
 * and WebSocket message processing.
 *
 * Dependencies: 00-config.js, 03-websocket.js, 04-cards.js, 05-chat.js
 * ======================================== */

async function showRecentConfigOptions(cardId, matches, tableColumns) {
    const optionsContainer = document.getElementById(`${cardId}-options`);
    if (!optionsContainer) {
        console.error('No options container found for cardId:', cardId);
        return;
    }
    
    // Clear existing content
    optionsContainer.innerHTML = '';
    
    // Find most recent 100% match only
    const perfectMatch = matches.find(config => {
        const matchScore = Math.round(config.match_score * 100);
        return matchScore === 100;
    });

    if (!perfectMatch) {
        // No perfect match - show only "Create with AI"
        showCreateWithAIButton(cardId);
        return;
    }

    // Show side-by-side buttons: "Use Match" (left) and "Create with AI" (right)
    showMatchAndCreateButtons(cardId, perfectMatch);
}

window.useMatchingConfig = async function(configKey, sourceSession) {
    // Declare cardId outside try so it's accessible in catch
    const uploadCard = document.querySelector('[data-card-id]');
    const cardId = uploadCard ? uploadCard.getAttribute('data-card-id') : 'upload';
    try {
        
        // Clear the input field and buttons before proceeding
        const inputField = document.getElementById(`${cardId}-config-id-input`);
        const optionsContainer = document.getElementById(`${cardId}-options`);
        if (inputField) inputField.style.display = 'none';
        if (optionsContainer) {
            const buttonContainer = optionsContainer.querySelector('[id$="-button-container"]');
            if (buttonContainer) buttonContainer.style.display = 'none';
        }
        
        showMessage(`${cardId}-messages`, 'Copying configuration from previous session...', 'info');
        
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'copyConfig',
                email: globalState.email,
                session_id: globalState.sessionId || '',
                source_config_key: configKey,
                source_session: sourceSession
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        if (!result.success) {
            throw new Error(result.error || 'Failed to copy configuration');
        }
        
        // Clear everything and show only success message like upload card does
        showFinalCardState(cardId, 'Configuration copied successfully! Generating preview...', 'success');
        
        // Update UI state
        globalState.configLoaded = true;
        globalState.configValidated = true;
        globalState.configStored = true;
        
        // Auto-generate preview after brief delay, like AI config does
        setTimeout(() => {
            createPreviewCard();
        }, 1500);
        
    } catch (error) {
        console.error('Error using matching config:', error);
        showMessage(`${cardId}-messages`, `Error copying configuration: ${error.message}`, 'error');
    }
}

async function useRecentConfig(cardId, configKey, sourceSession) {
    try {
        showMessage(`${cardId}-messages`, 'Copying configuration from previous session...', 'info');
        
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'copyConfig',
                email: globalState.email,
                session_id: globalState.sessionId || '',
                source_config_key: configKey,
                source_session: sourceSession
            })
        });
        
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error || 'Failed to copy configuration');
        }
        
        // Store the config in global state
        globalState.currentConfig = result.config_data;
        globalState.configStored = true;
        globalState.currentConfigId = result.config_id || configId;
        globalState.configSource = 'config_id';
        globalState.configMetadata = {
            config_id: result.config_id || configId,
            version: result.config_version,
            source_info: result.source_info,
            applied_at: new Date().toISOString()
        };
        
        // Show clean success state (no checkmark - green bar has one)
        showFinalCardState(cardId, 
            `Configuration ready from session: ${sourceSession}`, 
            'success'
        );
        
    } catch (error) {
        console.error('Error copying config:', error);
        showMessage(`${cardId}-messages`, `Error copying configuration: ${error.message}`, 'error');
    }
}

async function useConfigById(cardId, configId) {
    try {
        showMessage(`${cardId}-messages`, `Using configuration ID: ${configId}...`, 'info');
        
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'useConfigById',
                email: globalState.email,
                session_id: globalState.sessionId || '',
                config_id: configId
            })
        });
        
        // Check if response is ok before parsing JSON
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText || 'Unknown server error'}`);
        }
        
        // Check if response has content before parsing
        const responseText = await response.text();
        if (!responseText.trim()) {
            throw new Error('Empty response from server');
        }
        
        let result;
        try {
            result = JSON.parse(responseText);
        } catch (parseError) {
            throw new Error(`Invalid JSON response: ${parseError.message}`);
        }
        
        if (!result.success) {
            throw new Error(result.error || 'Failed to use configuration');
        }
        
        // Store the config in global state
        globalState.currentConfig = result.config_data;
        globalState.configStored = true;
        
        // Hide all card content and show only green success message
        const messagesContainer = document.getElementById(`${cardId}-messages`);
        const optionsContainer = document.getElementById(`${cardId}-options`);
        const buttonsContainer = document.getElementById(`${cardId}-buttons`);
        const configList = document.getElementById(`${cardId}-config-list`);
        
        // Hide all sections
        if (optionsContainer) optionsContainer.style.display = 'none';
        if (buttonsContainer) buttonsContainer.style.display = 'none';
        if (configList) configList.style.display = 'none';
        
        // Show only clean success message
        if (messagesContainer) {
            messagesContainer.innerHTML = `
                <div class="message message-success" style="margin-bottom: 1rem;">
                    <span class="message-icon">✓</span>
                    <span>Configuration applied successfully</span>
                </div>
            `;
        }
        
        // After successful config application, proceed to next step
        setTimeout(() => {
            createPreviewCard();
        }, 1000);
        
    } catch (error) {
        console.error('Error using config by ID:', error);
        showMessage(`${cardId}-messages`, `Error using configuration: ${error.message}`, 'error');
    }
}

function handleConfigIdInput(cardId) {
    const input = document.getElementById(`${cardId}-config-id-input`);
    if (!input) return;
    
    const configId = input.value.trim();
    if (!configId) return;
    
    // Secret upload functionality
    if (configId.toLowerCase() === 'upload') {
        // Trigger file upload
        const fileInput = document.getElementById(`${cardId}-config-file`);
        if (fileInput) {
            fileInput.click();
        } else {
            // Create a temporary file input
            const tempFileInput = document.createElement('input');
            tempFileInput.type = 'file';
            tempFileInput.accept = '.json';
            tempFileInput.style.display = 'none';
            tempFileInput.onchange = (e) => handleConfigUpload(e, cardId);
            document.body.appendChild(tempFileInput);
            tempFileInput.click();
            document.body.removeChild(tempFileInput);
        }
        // Clear the input
        input.value = '';
        return;
    }
    
    // Regular config ID usage
    useConfigById(cardId, configId);
}

// DEPRECATED: viewConfigInNewTab function removed in favor of config ID system
// All config references now use secure config IDs instead of download URLs

function showConfigIdInput(cardId) {
    const optionsContainer = document.getElementById(`${cardId}-options`);
    if (!optionsContainer) return;
    
    // Clear existing content
    optionsContainer.innerHTML = '';
    
    const inputContainer = document.createElement('div');
    inputContainer.style.cssText = `
        padding: 20px;
        border: 1px solid #ddd;
        border-radius: 8px;
        background: #f9f9f9;
    `;
    
    inputContainer.innerHTML = `
        <h4 style="margin: 0 0 15px 0; color: #333;">Enter Configuration ID</h4>
        <div style="background: #f8f9fa; padding: 12px; border-radius: 4px; margin-bottom: 15px; border-left: 4px solid var(--primary-color);">
            <strong>💡 Tip:</strong> Configuration IDs are the easiest way to reuse validated configurations. Check your validation results emails for IDs like <code>session_20250819_v1_financial_portfolio</code>
        </div>
        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
            <input type="text" id="${cardId}-config-id-input" placeholder="session_20250819_v1_financial_portfolio" 
                   style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; font-family: monospace;">
        </div>
        <div style="font-size: 13px; color: #666; margin-bottom: 15px;">
            📧 Find this ID in your validation results email<br>
            📋 Format: <code>sessionID_vVersion_description</code><br>
            ✅ Example: <code>session_20250819_v1_financial_portfolio</code>
        </div>
        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
            <button class="std-button primary" onclick="submitConfigId('${cardId}')">
                <span class="button-text">✅ Use Config</span>
            </button>
        </div>
        <button class="std-button secondary" style="width: 100%;" onclick="location.reload()">
            <span class="button-text">← Back to Options</span>
        </button>
    `;
    
    optionsContainer.appendChild(inputContainer);
    
    // Focus the input field
    setTimeout(() => {
        const input = document.getElementById(`${cardId}-config-id-input`);
        if (input) input.focus();
    }, 100);
}

function submitConfigId(cardId) {
    const input = document.getElementById(`${cardId}-config-id-input`);
    if (!input) return;
    
    const configId = input.value.trim();
    if (!configId) {
        showMessage(`${cardId}-messages`, 'Please enter a configuration ID', 'error');
        input.focus();
        return;
    }
    
    // Secret upload trigger - check if user typed "upload" (case insensitive)
    if (configId.toLowerCase() === 'upload') {
        showMessage(`${cardId}-messages`, 'Opening file picker...', 'info');
        
        // Trigger the hidden file input for config upload
        const fileInput = document.getElementById('config-upload-input');
        if (fileInput) {
            fileInput.click();
        } else {
            // Create hidden file input if it doesn't exist
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'file';
            hiddenInput.id = 'config-upload-input';
            hiddenInput.accept = '.json';
            hiddenInput.style.display = 'none';
            hiddenInput.onchange = function(e) {
                if (e.target.files.length > 0) {
                    handleConfigUpload(e.target.files[0], cardId);
                }
            };
            document.body.appendChild(hiddenInput);
            hiddenInput.click();
        }
        
        // Clear the input
        input.value = '';
        return;
    }
    
    // Enhanced validation for config ID format
    const configIdRegex = /^[a-zA-Z0-9_]+_v\d+/;
    if (!configIdRegex.test(configId)) {
        showMessage(`${cardId}-messages`, 'Invalid configuration ID format.<br><br>Expected format: sessionID_vVersion_description<br>Example: session_20250819_v1_financial_portfolio<br><br>Please check your validation results email for the correct ID.', 'error');
        input.focus();
        return;
    }
    
    // Check for minimum length to avoid obviously invalid IDs
    if (configId.length < 15) {
        showMessage(`${cardId}-messages`, 'Configuration ID appears too short. Please verify you have the complete ID from your email.', 'error');
        input.focus();
        return;
    }
    
    // Check for maximum reasonable length
    if (configId.length > 200) {
        showMessage(`${cardId}-messages`, 'Configuration ID is too long. Please check for any extra characters.', 'error');
        input.focus();
        return;
    }
    
    useConfigById(cardId, configId);
}

function generateWithAI(cardId) {
    // This should redirect to AI generation flow
    // For now, just clear and show AI option
    const optionsContainer = document.getElementById(`${cardId}-options`);
    if (!optionsContainer) return;
    
    optionsContainer.innerHTML = `
        <div style="padding: 20px; text-align: center; border: 1px solid #ddd; border-radius: 8px; background: #f0f8f0;">
            <h4 style="margin: 0 0 15px 0; color: #2d5a27;">🤖 AI Configuration Generation</h4>
            <p style="margin: 0 0 15px 0; color: #666;">
                AI configuration generation will analyze your table and create an optimal validation configuration.
            </p>
            <button class="std-button primary" style="width: 100%; margin-bottom: 10px;" onclick="proceedToAIGeneration('${cardId}')">
                <span class="button-text">🚀 Proceed with AI Generation</span>
            </button>
            <button class="std-button secondary" style="width: 100%;" onclick="location.reload()">
                <span class="button-text">← Back to Options</span>
            </button>
        </div>
    `;
}

function proceedToAIGeneration(cardId) {
    // Store that user wants AI generation and proceed to next step
    globalState.useAIGeneration = true;
    
    // Show success state for this card
    showFinalCardState(cardId, 
        'AI Configuration Generation selected', 
        'success'
    );
    
    // The workflow will continue with AI generation in the next step
}

async function validateRecentConfig(cardId) {
    // Create progress indicator like in config upload
    const progress = createProgress({
        title: 'Validating Configuration',
        messages: [
            'Checking configuration compatibility...',
            'Validating column targets...',
            'Verifying structure...'
        ],
        estimatedTime: 3000,
        containerId: `${cardId}-messages`
    });
    
    try {
        // Config validation using current session and stored config
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'validateConfig',
                email: globalState.email,
                session_id: globalState.sessionId || ''
            })
        });

        const result = await response.json();
        completeThinkingInCard(cardId, 'Configuration validated!');
        // Progress routed to card level;

        if (!result.success) {
            throw new Error(result.error || 'Configuration validation failed');
        }

        // Store the validated config and show results like upload pathway
        globalState.currentConfig = result.validated_config || globalState.currentConfig;
        globalState.configStored = true;

        // Show validation results in single green box
        showFinalCardState(cardId, 
            `Configuration validated successfully • ${result.valid_targets || 0} targets validated`, 
            'success'
        );

        // Automatically proceed to preview after validation
        setTimeout(() => {
            createPreviewCard();
        }, 1000);

    } catch (error) {
        console.error('Config validation error:', error);
        completeThinkingInCard(cardId, 'Validation failed');
        
        // Store error details for repair mode
        globalState.configError = error.message || 'Configuration validation failed';
        globalState.validationErrorDetails = {
            error: error.message,
            config: globalState.currentConfig,
            timestamp: new Date().toISOString()
        };
        
        // Show error with automatic repair option
        const messagesContainer = document.getElementById(`${cardId}-messages`);
        if (messagesContainer) {
            messagesContainer.innerHTML = `
                <div class="message message-error" style="margin-bottom: 1rem;">
                    <span class="message-icon"></span>
                    <span>Configuration validation failed: ${error.message}</span>
                </div>
                <div class="message message-info" style="margin-bottom: 1rem;">
                    <span class="message-icon">🔧</span>
                    <span>I'll automatically help you fix the configuration issues.</span>
                </div>
            `;
        }
        
        // Automatically create repair card with error context
        setTimeout(() => {
            createAutoRepairCard(error.message);
        }, 1500);
    }
}

// Create automatic repair card that passes validation errors to config lambda
function createAutoRepairCard(errorMessage) {
    const cardId = generateCardId();
    const content = `
        <div id="${cardId}-chat" class="chat-container"></div>
        <div id="${cardId}-refinement" style="display: none;">
            <textarea
                id="${cardId}-refinement-input"
                class="refinement-input"
                placeholder="The AI has detected the issues. You can provide additional guidance or simply submit for automatic repair..."
                data-error-message="${errorMessage.replace(/"/g, '&quot;')}"
                onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();const btn=document.querySelector('#${cardId}-buttons button.primary');if(btn){btn.focus();btn.classList.add('hover');setTimeout(()=>btn.classList.remove('hover'),1500);}}"
            ></textarea>
        </div>
        <div id="${cardId}-messages"></div>
    `;

    const card = createCard({
        id: cardId,
        icon: '🔧',
        title: 'Auto-Repair Configuration',
        subtitle: 'Fixing validation issues automatically',
        content
    });

    // Immediately start the repair process with the error details
    setTimeout(() => {
        startAutoConfigRepair(cardId, errorMessage);
    }, 500);

    return card;
}

async function startAutoConfigRepair(cardId, errorMessage) {
    // Show the error context and ask for additional guidance
    await addChatMessage(cardId, 'ai', 
        `I detected these validation issues with your configuration:\n\n**Error:** ${errorMessage}\n\n` +
        `I'll automatically fix these issues. You can provide additional guidance below, or simply click "Auto-Fix" to let me resolve the problems.`
    );

    // Show refinement input for optional additional guidance
    document.getElementById(`${cardId}-refinement`).style.display = 'block';
    const refinementInput = document.getElementById(`${cardId}-refinement-input`);
    if (refinementInput) {
        refinementInput.value = ''; // STANDARD PATTERN: Always clear text box when AI requests new input
    }
    
    // Add auto-fix and manual fix buttons
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Auto-Fix Issues',
            icon: '🤖',
            variant: 'primary',
            callback: async () => {
                // Auto-fix without additional user input
                await submitConfigRepairWithError(cardId, errorMessage, '');
            }
        },
        {
            text: 'Fix with Guidance',
            icon: '📤',
            variant: 'secondary',
            callback: async () => {
                const input = document.getElementById(`${cardId}-refinement-input`).value.trim();
                await submitConfigRepairWithError(cardId, errorMessage, input);
            }
        }
    ]);
}

// Submit config repair with validation error details
async function submitConfigRepairWithError(cardId, errorMessage, userGuidance) {
    // Hide input and buttons
    document.getElementById(`${cardId}-refinement`).style.display = 'none';
    const buttonsContainer = document.getElementById(`${cardId}-buttons`);
    if (buttonsContainer) buttonsContainer.style.display = 'none';

    // Add user guidance if provided
    if (userGuidance) {
        await addChatMessage(cardId, 'user', userGuidance);
    }

    // Show thinking indicators
    showThinkingInCard(cardId, 'Analyzing and fixing configuration issues...', true);
    startDummyProgress(cardId, 70000, 'config');

    try {
        // Prepare repair request with error details and current config
        const repairInstructions = `Fix these validation errors: ${errorMessage}` + 
            (userGuidance ? `\n\nAdditional guidance: ${userGuidance}` : '');
        
        const response = await fetch(`${API_BASE}/validate?async=true`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'repairConfig',
                email: globalState.email,
                session_id: globalState.sessionId,
                config_data: globalState.currentConfig, // Pass the problematic config
                validation_error: errorMessage, // Pass the specific error
                repair_instructions: repairInstructions,
                error_context: globalState.validationErrorDetails // Full error context
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Register WebSocket handler for repair completion
            unregisterCardHandler(cardId);
            registerCardHandler(cardId, ['config'], (wsData, handlerCardId) => {
                handleConfigRepairWebSocketMessage(wsData, handlerCardId);
            });
            
            if (data.session_id) {
                connectToSession(data.session_id);
            }
        } else {
            throw new Error(data.error || 'Configuration repair failed');
        }
    } catch (error) {
        completeThinkingInCard(cardId, 'Repair failed');
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

// WebSocket handler for config repair completion
async function handleConfigRepairWebSocketMessage(data, cardId) {
    if (data.type === 'config_generation_complete') {
        completeThinkingInCard(cardId, 'Configuration repaired!');
        
        globalState.currentConfig = data;
        globalState.excelFileUploaded = true;
        globalState.configError = null; // Clear error state
        globalState.validationErrorDetails = null;
        
        // Save clarifying questions for later use in refinement
        if (data.clarifying_questions) {
            globalState.savedQuestions = data.clarifying_questions;
        }
        
        let aiMessage = data.ai_summary || data.ai_response || 'Configuration issues have been fixed!';
        await addChatMessage(cardId, 'ai', aiMessage);
        
        // Show accept button and auto-generate preview
        createButtonRow(`${cardId}-buttons`, [
            {
                text: 'Accept Repaired Config',
                icon: '✅',
                variant: 'primary',
                callback: async (e) => {
                    const button = e.target.closest('button');
                    markButtonSelected(button, '✅ Accepted');
                    globalState.configValidated = true;
                    globalState.configStored = true;
                    
                    // Auto-generate preview of repaired config
                    setTimeout(() => {
                        createPreviewCard();
                    }, 1000);
                }
            }
        ]);
        
    } else if (data.type === 'config_generation_failed' || data.error || data.type === 'error') {
        completeThinkingInCard(cardId, 'Repair failed');
        const errorMessage = data.error || data.message || 'Configuration repair failed';
        showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');
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
            headers: getAuthHeaders(),
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

function offerConfigRepair(cardId, errorMessage, config) {
    const messagesEl = document.getElementById(`${cardId}-messages`);
    messagesEl.innerHTML += `
        <div class="message message-error">
            <span class="message-icon">❌</span>
            <span>Config Error: ${errorMessage}</span>
        </div>
    `;

    createButtonRow(`${cardId}-repair-buttons`, [
        {
            text: 'Repair Config',
            icon: '🔧',
            variant: 'primary',
            callback: async () => {
                globalState.configToRepair = config;
                globalState.configError = errorMessage;
                createAIConfigCard(true);
            }
        },
        {
            text: 'Generate New',
            icon: '✨',
            variant: 'secondary',
            callback: async () => createTableMakerCard()
        }
    ]);

    messagesEl.appendChild(document.getElementById(`${cardId}-repair-buttons`));
}

// selectCreateWithAI function removed - now handled inline in button callback

// Create a config card pre-filled with a specific config ID
async function createConfigCardWithId(configId) {
    const cardId = generateCardId();

    // Create the content structure with config input and messages
    const content = `
        <div id="${cardId}-config-list"></div>
        <div id="${cardId}-options" style="margin-top: 20px;">
            <div style="margin-bottom: 16px;">
                <input type="text"
                    id="${cardId}-config-id-input"
                    class="form-input"
                    placeholder="Reverting to previous configuration..."
                    style="width: 100%; text-align: center;"
                    data-card-id="${cardId}"
                    value="${configId}"
                    readonly
                />
            </div>
            <div id="${cardId}-button-container"></div>
        </div>
        <div id="${cardId}-messages"></div>
    `;

    // Create the card with appropriate title for revert
    const card = createCard({
        id: cardId,
        icon: '↩️',
        title: 'Revert Configuration',
        subtitle: 'Reverting to previous configuration and generating new preview',
        content
    });

    // Automatically submit the config ID after a short delay
    setTimeout(async () => {
        try {
            await useConfigById(cardId, configId);
            // After successfully using the config, auto-create preview
            setTimeout(() => {
                createPreviewCard();
            }, 1000);
        } catch (error) {
            console.error('Error reverting to config:', error);
            showMessage(`${cardId}-messages`, `Error reverting to previous configuration: ${error.message}`, 'error');
        }
    }, 500);

    return card;
}

function createConfigurationCard() {
    // Check if we have any good matches - if not, skip configuration card and go straight to table maker
    if (!globalState.matchingConfigs || !globalState.matchingConfigs.matches) {
        createTableMakerCard();
        return;
    }

    const goodMatches = globalState.matchingConfigs.matches.filter(match => match.match_score >= 0.8);
    if (goodMatches.length === 0) {
        createTableMakerCard();
        return;
    }

    const cardId = generateCardId();
    
    // Create the content structure with config input and messages
    const content = `
        <div id="${cardId}-config-list"></div>
        <div id="${cardId}-options" style="margin-top: 20px;">
            <div style="margin-bottom: 16px;">
                <input type="text" 
                    id="${cardId}-config-id-input" 
                    class="form-input" 
                    placeholder="I have a configuration code!" 
                    style="width: 100%; text-align: center;"
                    data-card-id="${cardId}"
                />
            </div>
            <div id="${cardId}-button-container"></div>
        </div>
        <div id="${cardId}-messages"></div>
    `;

    // Create the card
    const card = createCard({
        id: cardId,
        icon: '⚙️',
        title: 'Configuration',
        subtitle: 'Identify a configuration file with table metadata and research strategy',
        content
    });

    // Hidden file input for config upload
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.json';
    fileInput.style.display = 'none';
    fileInput.id = `${cardId}-config-file`;
    fileInput.onchange = (e) => handleConfigUpload(e, cardId);
    card.appendChild(fileInput);

    // Setup event handlers after DOM is ready
    setTimeout(() => {
        // Config ID input event listeners
        const configInput = document.getElementById(`${cardId}-config-id-input`);
        if (configInput) {
            // Focus/blur handlers for placeholder
            configInput.addEventListener('focus', () => {
                configInput.placeholder = 'Enter configuration ID...';
            });
            
            configInput.addEventListener('blur', () => {
                if (configInput.value === '') {
                    configInput.placeholder = 'I have a configuration code!';
                }
            });
            
            // Enter key handler
            configInput.addEventListener('keydown', async (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const cardIdFromInput = configInput.getAttribute('data-card-id');
                    if (cardIdFromInput) {
                        await handleConfigIdInput(cardIdFromInput);
                    }
                }
            });
        }

        // Now populate the green buttons based on matching configs

        const buttonContainer = document.getElementById(`${cardId}-button-container`);
        if (buttonContainer) {
            if (globalState.matchingConfigs && globalState.matchingConfigs.matches) {
                const goodMatches = globalState.matchingConfigs.matches.filter(match => match.match_score >= 0.8);

                if (goodMatches.length > 0) {
                    // Check for perfect matches
                    const perfectMatch = goodMatches.find(config => {
                        const matchScore = Math.round(config.match_score * 100);
                        return matchScore === 100;
                    });
                    
                    if (perfectMatch) {
                        buttonContainer.innerHTML = `
                            <div style="display: flex; gap: 10px; margin: 20px 0;">
                                <button class="std-button primary" onclick="useMatchingConfig('${perfectMatch.config_s3_key}', '${perfectMatch.source_session}')" style="flex: 1;">
                                    <span class="button-text">🔗 Use Match (100%)</span>
                                </button>
                                <button class="std-button secondary" onclick="startUploadInterviewFromConfig()" style="flex: 1;">
                                    <span class="button-text">🤖 Create with AI</span>
                                </button>
                            </div>
                        `;
                    } else {
                        buttonContainer.innerHTML = `
                            <div style="margin: 20px 0; text-align: center;">
                                <button class="std-button secondary" onclick="startUploadInterviewFromConfig()">
                                    <span class="button-text">🤖 Create with AI</span>
                                </button>
                            </div>
                        `;
                    }
                } else {
                    buttonContainer.innerHTML = `
                        <div style="margin: 20px 0; text-align: center;">
                            <button class="std-button secondary" onclick="startUploadInterviewFromConfig()" style="background: #6b46c1; border-color: #6b46c1; color: white;">
                                <span class="button-text">🤖 Create with AI</span>
                            </button>
                        </div>
                    `;
                }
            } else {
                buttonContainer.innerHTML = `
                    <div style="margin: 20px 0; text-align: center;">
                        <button class="std-button secondary" onclick="startUploadInterviewFromConfig()" style="background: #6b46c1; border-color: #6b46c1; color: white;">
                            <span class="button-text">🤖 Create with AI</span>
                        </button>
                    </div>
                `;
            }
        }
    }, 100);

    return card;
}
// 4. AI Configuration Card
window.createAIConfigCard = function(isRepair = false) {
    // DEPRECATED: Non-repair mode (isRepair=false) is deprecated.
    // Use createTableMakerCard() instead for de-novo table creation.
    // Only repair mode (isRepair=true) should use this function.
    if (!isRepair) {
        console.warn('[DEPRECATED] createAIConfigCard(false) is deprecated. Use createTableMakerCard() instead.');
        // Redirect to table maker for better UX
        createTableMakerCard();
        return;
    }

    const cardId = generateCardId();
    const content = `
        <div id="${cardId}-progress"></div>
        <div id="${cardId}-chat" class="chat-container"></div>
        <div id="${cardId}-refinement" style="display: none;">
            <textarea
                id="${cardId}-refinement-input"
                class="refinement-input"
                placeholder="Describe how you'd like to refine the configuration..."
            ></textarea>
        </div>
        <div id="${cardId}-messages"></div>
    `;

    const card = createCard({
        id: cardId,  // Pass explicit ID
        icon: '🤖',
        title: 'Repair Configuration',
        subtitle: 'Fixing configuration issues',
        content
    });

    // Start config repair (only repair mode supported now)
    startConfigRepair(cardId);

    return card;
}

// Create refinement card specifically for post-preview refinement
window.createRefinementCard = async function() {
    const cardId = generateCardId();

    // DEBUG: Check what questions are available right now
    if (globalState.currentConfig) {
        if (globalState.currentConfig.clarifying_questions) {
        }
    }
    
    const content = `
        <div id="${cardId}-chat" class="chat-container"></div>
        <div id="${cardId}-refinement" style="display: block;">
            <textarea
                id="${cardId}-refinement-input"
                class="refinement-input"
                placeholder="Describe how you'd like to refine the configuration based on the preview results..."
                onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();const btn=document.querySelector('#${cardId}-buttons button.primary');if(btn){btn.focus();btn.classList.add('hover');setTimeout(()=>btn.classList.remove('hover'),1500);}}"
            ></textarea>
        </div>
        <div id="${cardId}-progress"></div>
        <div id="${cardId}-messages"></div>
    `;

    const card = createCard({
        id: cardId,
        icon: '🔧',
        title: 'Refine Configuration',
        subtitle: 'Improve configuration based on preview results',
        content,
        buttons: [
            {
                text: 'Submit',
                variant: 'primary',
                width: 'full',
                callback: async (e) => {
                    const button = e.target.closest('button');
                    const input = document.getElementById(`${cardId}-refinement-input`).value.trim();
                    if (!input) {
                        showMessage(`${cardId}-messages`, 'Please enter refinement instructions', 'error');
                        return;
                    }
                    markButtonSelected(button, 'Thinking...');
                    await submitConfigRefinementWithAutoPreview(cardId, input);
                }
            }
        ]
    });

    // Always unregister first to prevent duplicates
    unregisterCardHandler(cardId);
    
    registerCardHandler(cardId, ['config'], (wsData, handlerCardId) => {
        handleConfigWebSocketMessage(wsData, handlerCardId);
    });

    // Add initial AI message with questions if available
    
    let questionsToShow = null;
    if (globalState.savedQuestions) {
        questionsToShow = globalState.savedQuestions;
    } else if (globalState.currentConfig?.clarifying_questions) {
        questionsToShow = globalState.currentConfig.clarifying_questions;
    } else {
    }

    // If no questions found anywhere, try to fetch from backend as fallback
    if (!questionsToShow && globalState.email && globalState.sessionId) {
        try {
            const backendResult = await fetchClarifyingQuestionsFromBackend(
                globalState.email,
                globalState.sessionId
            );
            if (backendResult && backendResult.questions) {
                questionsToShow = backendResult.questions;
                // Also save to global state for future use
                globalState.savedQuestions = questionsToShow;
            }
        } catch (error) {
            console.error('[ERROR] Backend fallback failed:', error);
        }
    }

    // Determine if we're refining from preview or full validation results
    let initialMessage;
    if (globalState.completionData) {
        initialMessage = 'What did you like and not like about the full validation results?';
    } else {
        initialMessage = 'What did you like and not like about the preview results?';
    }
    
    if (questionsToShow) {
        initialMessage += '\n\nHere are some specific questions to consider:\n\n' + questionsToShow;
    } else {
    }
    
    await addChatMessage(cardId, 'ai', initialMessage);

    return card;
}

// DEPRECATED: This flow is replaced by the interactive table maker conversation.
// Use createTableMakerCard() instead for de-novo table creation.
// Keeping these functions commented for reference, but they should not be called.
/*
async function startConfigGeneration(cardId) {
    // DEPRECATED: Use createTableMakerCard() for new table creation
    console.error('[DEPRECATED] startConfigGeneration is deprecated. Use createTableMakerCard() instead.');
    // First, show the initial table questions instead of immediately generating
    await showInitialTableQuestions(cardId);
}

async function showInitialTableQuestions(cardId) {
    // DEPRECATED: Use createTableMakerCard() for new table creation
    console.error('[DEPRECATED] showInitialTableQuestions is deprecated. Use createTableMakerCard() instead.');

    const chatContainer = document.getElementById(`${cardId}-chat`);
    if (chatContainer) {
        chatContainer.style.display = 'block';
    }

    // Add initial AI message with generic table questions
    const initialQuestions = `Let's build an initial configuration together that clarifies what the table and columns are about and that specifies an optimized approach to validating this table.

**The following questions are optional but will help us create a more targeted configuration:**

1. **Primary Purpose**: Are you looking to gather research from the internet, fact-check existing entries, or update the information in the table?

2. **Row Identifiers**: Which columns identify the row?

3. **Table Context**: Who uses this table and for what purpose?

4. **Column Meaning**: Specify intent for columns that are not self-evident in the table.

5. **Dependencies**: Are any columns calculated from other columns, or do they require information not available online?

6. **Other Requirements**: Do you have specific requirements for validation (general or for specific columns)? Examples: academic sources only, data about upcoming events.

Our initial configuration will balance cost and accuracy by using efficient models and targeted searching. After reviewing the preview results, you can use the "Refine Configuration" button to selectively apply more powerful models and deeper analysis to specific areas that need improvement. The goal is to arrive at an optimal configuration that we can use for tables with the same columns down the road.

Please provide any additional context, or simply proceed to generate your initial configuration.`;

    await addChatMessage(cardId, 'ai', initialQuestions);


    // Show refinement input for answers
    const refinementContainer = document.getElementById(`${cardId}-refinement`);
    if (refinementContainer) {
        refinementContainer.style.display = 'block';
        const input = document.getElementById(`${cardId}-refinement-input`);
        if (input) {
            input.placeholder = 'Please answer the questions above to help me create the best configuration for your table...';
            input.onkeydown = (event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    const userInput = input.value.trim();
                    // Trigger the submit button click
                    refinementContainer.style.display = 'none';
                    const buttonsContainer = document.getElementById(`${cardId}-buttons`);
                    if (buttonsContainer) buttonsContainer.style.display = 'none';
                    addChatMessage(cardId, 'user', userInput).then(() => {
                        startConfigGenerationWithContext(cardId, userInput);
                    });
                }
            };
        }
    }

    // Add submit button
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Submit',
            variant: 'primary',
            callback: debounceConfigAction(`generate-config-${cardId}`, async (e) => {
                const button = e.target.closest('button');
                const input = document.getElementById(`${cardId}-refinement-input`).value.trim();

                // Mark button as thinking
                markButtonSelected(button, 'Thinking...');

                // Hide the input (keep button visible to show thinking state)
                refinementContainer.style.display = 'none';

                // Add user answers to chat
                await addChatMessage(cardId, 'user', input);

                // Now start the actual config generation with the context
                await startConfigGenerationWithContext(cardId, input);
            })
        }
    ]);
}
*/

// DEPRECATED: Use createTableMakerCard() for new table creation
// This function is kept for legacy compatibility but should not be called for new table creation.
async function startConfigGenerationWithContext(cardId, userAnswers) {
    console.error('[DEPRECATED] startConfigGenerationWithContext is deprecated. Use createTableMakerCard() instead.');
    console.warn('[DEPRECATED] Redirecting to table maker for better user experience...');

    // Redirect to table maker for better UX
    createTableMakerCard();
    return;

    // Legacy code below (unreachable, kept for reference)
    // Show thinking indicators
    showThinkingInCard(cardId, 'Starting configuration generation...', true);
    // Start config-specific dummy progress animation
    startDummyProgress(cardId, 70000, 'config'); // 70 seconds estimated for config generation
    // Progress routed to card level;
    
    try {
        // First, upload Excel file if not already uploaded to unified storage
        if (!globalState.excelFileUploaded) {
            const formData = new FormData();
            formData.append('excel_file', globalState.excelFile);
            formData.append('email', globalState.email);
            // Only append session_id if we have one (for new uploads, backend will generate)
            if (globalState.sessionId) {
                formData.append('session_id', globalState.sessionId);
            }

            const uploadResponse = await fetch(`${API_BASE}/validate`, {
                method: 'POST',
                body: formData
            });

            if (!uploadResponse.ok) {
                const errorText = await uploadResponse.text();
                console.error('[ERROR] Config generation upload failed with status:', uploadResponse.status);
                throw new Error(`Failed to upload Excel file to unified storage: ${uploadResponse.status} - ${errorText}`);
            }

            const uploadData = await uploadResponse.json();
            
            // Validate the response
            if (!uploadData.success) {
                throw new Error(`Upload failed: ${uploadData.error || 'Unknown error'}`);
            }
            globalState.excelFileUploaded = true;
            
            // Update session ID from backend response
            if (uploadData.session_id) {
                saveSessionId(uploadData.session_id);
            }
            
            // Store the storage path for reference
            if (uploadData.storage_path) {
                globalState.storagePath = uploadData.storage_path;
            }
        }

        // Now request config generation (no need to re-upload Excel)
        const response = await fetch(`${API_BASE}/validate?async=true`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'generateConfig',
                email: globalState.email,
                session_id: globalState.sessionId || '',
                instructions: `Generate an optimal configuration for this data validation scenario. User provided these answers to clarifying questions: ${userAnswers}`
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            
            // Check if this is a synchronous completion (config generated immediately)
            if (data.ai_summary && data.download_url) {
                // Handle synchronous config generation completion
                completeThinkingInCard(cardId, 'Configuration generated!');
                
                globalState.currentConfig = data;
                globalState.excelFileUploaded = true;
                
                // Save clarifying questions for later use in refinement
                if (data.clarifying_questions) {
                    globalState.savedQuestions = data.clarifying_questions;
                }
                
                let aiMessage = data.ai_summary || data.ai_response || 'Configuration generated successfully!';
                await addChatMessage(cardId, 'ai', aiMessage);
                
                // Add config ID display if available
                if (data.config_id || data.session_id) {
                    const chatContainer = document.getElementById(`${cardId}-chat`);
                    if (chatContainer) {
                        const configIdDiv = document.createElement('div');
                        configIdDiv.className = 'chat-message ai';
                        const version = data.config_version || 1;
                        const configId = data.config_id || `${data.session_id}_v${version}`;
                        configIdDiv.innerHTML = `
                            <div class="config-id-display" style="margin-top: 16px; padding: 16px; background: linear-gradient(135deg, #f0f8ff 0%, #e8f4fd 100%); border-radius: 8px; border: 1px solid #b3d9ff;">
                                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                                    <span style="font-size: 18px; margin-right: 8px;">🆔</span>
                                    <strong style="color: #2c5530;">Configuration ID Generated</strong>
                                </div>
                                <div style="background: white; padding: 12px; border-radius: 4px; border: 1px solid #ddd; margin-bottom: 8px;">
                                    <code style="font-size: 16px; font-weight: bold; color: #1a472a; font-family: 'Courier New', monospace;">${configId}</code>
                                </div>
                                <div style="font-size: 14px; color: #555; line-height: 1.4;">
                                    <div style="margin-bottom: 4px;">💾 <strong>Save this ID</strong> - it will be included in your validation results email</div>
                                    <div style="margin-bottom: 4px;">🔄 <strong>Reuse anywhere</strong> - enter this ID to apply the same configuration to future validations</div>
                                    <div>🔒 <strong>Secure</strong> - share this ID safely without exposing configuration details</div>
                                </div>
                            </div>
                        `;
                        chatContainer.appendChild(configIdDiv);
                    }
                }
                
                // Create accept button and auto-generate preview
                createButtonRow(`${cardId}-buttons`, [
                    {
                        text: 'Accept & Generate Preview',
                        icon: '✅',
                        variant: 'primary',
                        callback: async (e) => {
                            const button = e.target.closest('button');
                            markButtonSelected(button, '✅ Accepted');
                            // Auto-generate preview immediately
                            setTimeout(() => {
                                createPreviewCard();
                            }, 1000);
                        }
                    }
                ]);
            } else {
                // Even if async, save any clarifying questions from immediate response
                if (data.clarifying_questions) {
                    globalState.savedQuestions = data.clarifying_questions;
                }
                
                // Continue showing thinking indicators for async WebSocket completion
                updateThinkingInCard(cardId, 'AI analyzing table structure...');
                // Progress routed to card level;

                const sessionIdForSocket = data.session_id || globalState.sessionId;
                
                // Register WebSocket handler for this card
                unregisterCardHandler(cardId);
                registerCardHandler(cardId, ['config'], (wsData, handlerCardId) => {
                    handleConfigWebSocketMessage(wsData, handlerCardId);
                });
                
                ensureWebSocketHealth(sessionIdForSocket);
            }
        } else {
            // Enhanced error handling with retry suggestions
            let errorMessage = data.error || 'Failed to start generation';
            
            if (data.retry_suggestion) {
                errorMessage += `\n\n💡 Suggestion: ${data.retry_suggestion}`;
            }
            
            if (data.error_type === 'format_error') {
                errorMessage += '\n\n🔄 You can try generating the configuration again with simpler instructions.';
                throw new Error(errorMessage);
            } else if (data.error_type === 'api_overloaded') {
                // Show blue info notification for API overload instead of error
                completeThinkingInCard(cardId, 'Generation paused');
                showMessage(`${cardId}-messages`, 'ℹ️ Claude API is temporarily overloaded. This happens sometimes during peak usage. Please try again in 5-15 minutes and the submission button will be re-enabled.', 'info');
                return; // Don't throw error, just return to show the configuration card again
            }
            
            throw new Error(errorMessage);
        }
    } catch (error) {
        completeThinkingInCard(cardId, 'Generation failed');
        // Progress routed to card level;
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}
async function startConfigRepair(cardId) {
    // Show error context
    await addChatMessage(cardId, 'ai', 
        `I found some issues with your configuration:\n\n${globalState.configError}\n\n` +
        `Please describe how you'd like me to fix these issues.`
    );

    // Show refinement input and clear previous text
    document.getElementById(`${cardId}-refinement`).style.display = 'block';
    const refinementInput = document.getElementById(`${cardId}-refinement-input`);
    if (refinementInput) {
        refinementInput.value = ''; // STANDARD PATTERN: Always clear text box when AI requests new input
        refinementInput.onkeydown = (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                const input = refinementInput.value.trim();
                if (!input) {
                    showMessage(`${cardId}-messages`, 'Please enter repair instructions', 'error');
                    return;
                }
                submitConfigRefinementWithAutoPreview(cardId, input);
            }
        };
    }

    // Add submit button
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Submit',
            icon: '📤',
            callback: async () => {
                const input = document.getElementById(`${cardId}-refinement-input`).value.trim();
                if (!input) {
                    showMessage(`${cardId}-messages`, 'Please enter repair instructions', 'error');
                    return;
                }
                await submitConfigRefinementWithAutoPreview(cardId, input);
            }
        }
    ]);
}

// Handle WebSocket messages for config generation
async function handleConfigWebSocketMessage(data, cardId) {
    if (data.type === 'config_generation_progress') {
        // Update progress indicator with message from backend
        const progressPercent = data.progress || 0;
        const message = data.message || data.status || 'Processing...';
        updateThinkingProgress(cardId, progressPercent, message);
        return;
    }

    if (data.type === 'config_generation_complete') {
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

        // Add config ID display if available
        if (data.config_id || data.session_id) {
            const chatContainer = document.getElementById(`${cardId}-chat`);
            if (chatContainer) {
                const configIdDiv = document.createElement('div');
                configIdDiv.className = 'chat-message ai';
                const version = data.config_version || 1;
                const configId = data.config_id || `${data.session_id}_v${version}`;
                configIdDiv.innerHTML = `
                    <div class="config-id-display" style="margin-top: 16px; padding: 16px; background: linear-gradient(135deg, #f0f8ff 0%, #e8f4fd 100%); border-radius: 8px; border: 1px solid #b3d9ff;">
                        <div style="display: flex; align-items: center; margin-bottom: 8px;">
                            <span style="font-size: 18px; margin-right: 8px;">🆔</span>
                            <strong style="color: #2c5530;">Configuration ID Generated</strong>
                        </div>
                        <div style="background: white; padding: 12px; border-radius: 4px; border: 1px solid #ddd; margin-bottom: 8px;">
                            <code style="font-size: 16px; font-weight: bold; color: #1a472a; font-family: 'Courier New', monospace;">${configId}</code>
                        </div>
                        <div style="font-size: 14px; color: #555; line-height: 1.4;">
                            <div style="margin-bottom: 4px;">💾 <strong>Save this ID</strong> - it will be included in your validation results email</div>
                            <div style="margin-bottom: 4px;">🔄 <strong>Reuse anywhere</strong> - enter this ID to apply the same configuration to future validations</div>
                            <div>🔒 <strong>Secure</strong> - share this ID safely without exposing configuration details</div>
                        </div>
                    </div>
                `;
                chatContainer.appendChild(configIdDiv);
            }
        }

        // Show config actions
        showConfigActions(cardId);

    } else if (data.type === 'config_generation_failed' || data.error || data.type === 'error') {
        completeThinkingInCard(cardId, 'Generation failed');
        const errorMessage = data.error || data.message || 'Configuration generation failed';
        showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');
    }
}

async function addChatMessage(cardId, type, content, isUrgent = false, streamingType = 'normal') {
    const chatContainer = document.getElementById(`${cardId}-chat`);
    if (!chatContainer) return;

    const messageDiv = document.createElement('div');
    let className = `chat-message ${type}`;
    if (isUrgent) className += ' urgent';
    
    messageDiv.className = className;
    messageDiv.style.opacity = '0';
    chatContainer.appendChild(messageDiv);

    // Animate message appearance
    setTimeout(() => {
        messageDiv.style.opacity = '1';
    }, 100);

    // Stream text if it's an AI message
    if (type === 'ai') {
        if (streamingType === 'paragraphs') {
            await streamParagraphs(messageDiv, content);
        } else {
            await streamText(messageDiv, content);
        }
    } else {
        // For user messages, truncate if very long (pasted documents)
        let displayContent = content;
        if (content.length > 500) {
            displayContent = content.substring(0, 500) + '... [' + (content.length - 500) + ' more characters]';
        }
        messageDiv.innerHTML = renderMarkdown(displayContent);
        messageDiv.title = 'Click to expand'; // Tooltip

        // Add click to expand for truncated messages
        if (content.length > 500) {
            messageDiv.style.cursor = 'pointer';
            messageDiv.onclick = function() {
                if (this.innerHTML.includes('more characters]')) {
                    this.innerHTML = renderMarkdown(content);
                    this.title = 'Click to collapse';
                } else {
                    this.innerHTML = renderMarkdown(displayContent);
                    this.title = 'Click to expand';
                }
            };
        }
    }

    // Scroll to bottom - defer to avoid forced reflow
    requestAnimationFrame(() => {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    });
}

// Stream text with pauses at punctuation
async function streamText(element, text) {
    const htmlText = renderMarkdown(text);

    // For complex markdown (lists, headers), render instantly to preserve formatting
    if (text.includes('\n-') || text.includes('\n*') || text.includes('\n#') || text.includes('```')) {
        element.innerHTML = htmlText;
        return;
    }

    // For simple markdown (just bold/italic), stream by words
    const words = text.split(' ');
    let currentText = '';

    for (let i = 0; i < words.length; i++) {
        currentText += (i > 0 ? ' ' : '') + words[i];
        element.innerHTML = renderMarkdown(currentText);
        await sleep(27); // ~37 words per second (1.5x faster than 40ms)
    }
}

// Utility function for delays
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Fast paragraph-by-paragraph streaming for AI summaries
async function streamParagraphs(element, text) {
    // Convert markdown to HTML first
    const htmlText = renderMarkdown(text);
    
    // Check if content has markdown formatting
    if (htmlText !== text.replace(/\n/g, '<br>') || text.includes('**') || text.includes('*') || text.includes('#') || text.includes('`') || text.includes('[')) {
        // For markdown content, split by paragraphs but render as HTML
        const paragraphs = text.split(/\n\s*\n/); // Split on double line breaks
        let currentContent = '';
        
        for (let i = 0; i < paragraphs.length; i++) {
            if (paragraphs[i].trim()) {
                currentContent += paragraphs[i].trim() + '\n\n';
                element.innerHTML = renderMarkdown(currentContent);
                await sleep(500); // 0.5s between paragraphs
            }
        }
        return;
    }
    
    // For plain text, use paragraph streaming
    const paragraphs = text.split(/\n\s*\n/);
    let currentContent = '';
    
    for (let i = 0; i < paragraphs.length; i++) {
        if (paragraphs[i].trim()) {
            currentContent += paragraphs[i].trim() + '\n\n';
            element.textContent = currentContent;
            await sleep(500); // 0.5s between paragraphs
        }
    }
}

function showConfigActions(cardId) {
    // Clear any existing buttons
    const existingButtons = document.getElementById(`${cardId}-buttons`);
    if (existingButtons) existingButtons.remove();

    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Refine',
            icon: '🔧',
            variant: 'secondary',
            width: 1,
            callback: async (e) => {
                const button = e.target.closest('button');
                markButtonSelected(button, '🔧 Refining...');
                
                // Show simple processing message in same card and hide chat initially
                const messagesContainer = document.getElementById(`${cardId}-messages`);
                const chatContainer = document.getElementById(`${cardId}-chat`);
                if (messagesContainer) {
                    messagesContainer.innerHTML = `
                        <div class="message message-info" style="margin-bottom: 1rem;">
                            <span class="message-icon">🔧</span>
                            <span>Preparing refinement interface...</span>
                        </div>
                    `;
                }
                
                // Hide buttons while showing refinement interface
                const buttonsContainer = document.getElementById(`${cardId}-buttons`);
                if (buttonsContainer) buttonsContainer.style.display = 'none';
                
                await showRefinementInterface(cardId);
            }
        },
        {
            text: 'Accept',
            icon: '✅',
            variant: 'primary',
            width: 2,
            callback: async (e) => {
                const button = e.target.closest('button');
                markButtonSelected(button, '✅ Accepted');
                globalState.configValidated = true;
                globalState.configStored = true;
                globalState.configIsAI = true;
                
                // Show simple success message and clean up entire card
                const messagesContainer = document.getElementById(`${cardId}-messages`);
                const chatContainer = document.getElementById(`${cardId}-chat`);
                const buttonsContainer = document.getElementById(`${cardId}-buttons`);
                const refinementContainer = document.getElementById(`${cardId}-refinement`);
                
                // Hide all card content
                if (chatContainer) chatContainer.style.display = 'none';
                if (buttonsContainer) buttonsContainer.style.display = 'none';
                if (refinementContainer) refinementContainer.style.display = 'none';
                
                // Show only success message (no checkmark icon - green bar has one)
                if (messagesContainer) {
                    messagesContainer.innerHTML = `
                        <div class="message message-success" style="margin-bottom: 1rem;">
                            <span class="message-icon"></span>
                            <span>Configuration accepted and ready for processing.</span>
                        </div>
                    `;
                }
                
                setTimeout(() => createPreviewCard(), 1000);
            }
        }
    ]);
}

// Helper function to fetch clarifying questions from backend
async function fetchClarifyingQuestionsFromBackend(email, sessionId, configId = null) {
    try {

        const payload = {
            action: 'getAiSummary',
            email: email,
            session_id: sessionId
        };

        if (configId) {
            payload.config_id = configId;
        }

        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // DEBUG: Log full response to understand what we're getting
        // Backend error received

        if (data.success && data.clarifying_questions) {
            return {
                questions: data.clarifying_questions,
                urgency: data.clarification_urgency || 0,
                aiSummary: data.ai_summary || '',
                configVersion: data.config_version || 1
            };
        } else {
            return null;
        }
    } catch (error) {
        console.error('[ERROR] Error fetching clarifying questions from backend:', error);
        return null;
    }
}

// Helper function to extract clarifying questions from the latest config change log entry
function getQuestionsFromChangeLog(config) {
    
    if (!config) {
        return null;
    }
    
    // Check if this is a WebSocket response rather than a config
    if (config.type && config.session_id) {
        return null;
    }
    
    if (!config.config_change_log || !Array.isArray(config.config_change_log)) {
        return null;
    }
    
    
    // Get the latest entry from config_change_log that has clarifying_questions
    for (let i = config.config_change_log.length - 1; i >= 0; i--) {
        const entry = config.config_change_log[i];
        if (entry.clarifying_questions) {
            return entry.clarifying_questions;
        }
    }
    
    return null;
}

async function showRefinementInterface(cardId) {
    
    try {
        // Show chat container again for refinement interaction
        const chatContainer = document.getElementById(`${cardId}-chat`);
        const messagesContainer = document.getElementById(`${cardId}-messages`);
        if (chatContainer) chatContainer.style.display = 'block';
        if (messagesContainer) messagesContainer.innerHTML = ''; // Clear processing message
    
    // Always show questions from any available source
    
    let questionsToShow = null;
    
    // Check multiple locations for the actual config data
    let actualConfig = null;
    if (globalState.currentConfig) {
        // The WebSocket response might have the config nested in different ways
        if (globalState.currentConfig.config_data) {
            actualConfig = globalState.currentConfig.config_data;
        } else if (globalState.currentConfig.config) {
            actualConfig = globalState.currentConfig.config;
        } else if (globalState.currentConfig.config_change_log) {
            // It's already the config itself
            actualConfig = globalState.currentConfig;
        }
    }
    
    
    // Priority: saved questions from WebSocket response, then current config questions directly, then config change log
    if (globalState.savedQuestions) {
        questionsToShow = globalState.savedQuestions;
    } else if (globalState.currentConfig && globalState.currentConfig.clarifying_questions) {
        questionsToShow = globalState.currentConfig.clarifying_questions;
    } else {
        // Only try change log if we have an actual config structure
        const changeLogQuestions = actualConfig ? getQuestionsFromChangeLog(actualConfig) : null;
        if (changeLogQuestions) {
            questionsToShow = changeLogQuestions;
        } else if (actualConfig && actualConfig.clarifying_questions) {
            questionsToShow = actualConfig.clarifying_questions;
        } else {
        }
    }

    // If no questions found anywhere, try to fetch from backend as fallback
    if (!questionsToShow && globalState.email && globalState.sessionId) {
        try {
            const backendResult = await fetchClarifyingQuestionsFromBackend(
                globalState.email,
                globalState.sessionId
            );
            if (backendResult && backendResult.questions) {
                questionsToShow = backendResult.questions;
                // Also save to global state for future use
                globalState.savedQuestions = questionsToShow;
            }
        } catch (error) {
            console.error('[ERROR] Backend fallback failed in refinement:', error);
        }
    }

    // First paragraph: Ask about preview-based changes
    const initialMessage = `What did you like and not like about the preview results?`;
    await addChatMessage(cardId, 'ai', initialMessage);
    
    // Second paragraph: Show saved questions or generic options
    if (questionsToShow) {
        const questionsMessage = `Here are some specific questions to help refine the configuration:\n\n${questionsToShow}`;
        await addChatMessage(cardId, 'ai', questionsMessage, false, 'paragraphs');
    } else {
        // If no questions available, show a generic refinement prompt as second paragraph
        const genericMessage = `You can ask me to:\n\n` +
            `• Adjust validation targets or confidence levels\n` +
            `• Modify search strategies or groupings\n` +
            `• Change field importance or requirements\n` +
            `• Update model selections or search contexts`;
        await addChatMessage(cardId, 'ai', genericMessage, false, 'paragraphs');
    }

    // Show refinement input and clear previous text
    document.getElementById(`${cardId}-refinement`).style.display = 'block';
    const refinementInput = document.getElementById(`${cardId}-refinement-input`);
    refinementInput.value = ''; // STANDARD PATTERN: Always clear text box when AI requests new input
    refinementInput.focus();
    refinementInput.onkeydown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            const input = refinementInput.value.trim();
            if (!input) {
                showMessage(`${cardId}-messages`, 'Please enter refinement instructions', 'error');
                return;
            }
            submitConfigRefinementWithAutoPreview(cardId, input);
        }
    };

    // Update buttons - include both Submit and Accept options
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Submit',
            variant: 'secondary',
            width: 'full',
            callback: async (e) => {
                const button = e.target.closest('button');
                const input = document.getElementById(`${cardId}-refinement-input`).value.trim();
                if (!input) {
                    showMessage(`${cardId}-messages`, 'Please enter refinement instructions', 'error');
                    return;
                }
                
                // Mark button as thinking and disabled
                markButtonSelected(button, 'Thinking...');
                
                // Hide all content and show completion message
                const messagesContainer = document.getElementById(`${cardId}-messages`);
                const chatContainer = document.getElementById(`${cardId}-chat`);
                const refinementContainer = document.getElementById(`${cardId}-refinement`);
                
                if (chatContainer) chatContainer.style.display = 'none';
                if (refinementContainer) refinementContainer.style.display = 'none';
                
                if (messagesContainer) {
                    messagesContainer.innerHTML = `
                        <div class="message message-success" style="margin-bottom: 1rem;">
                            <span class="message-icon"></span>
                            <span>Refinement submitted successfully</span>
                        </div>
                    `;
                }
                
                await submitConfigRefinementWithAutoPreview(cardId, input);
            }
        },
        {
            text: 'Accept Configuration',
            icon: '✅',
            variant: 'primary',
            callback: async (e) => {
                const button = e.target.closest('button');
                markButtonSelected(button, '✅ Accepted');
                globalState.configValidated = true;
                globalState.configStored = true;
                globalState.configIsAI = true;
                
                // Show simple success message and clean up entire card
                const messagesContainer = document.getElementById(`${cardId}-messages`);
                const chatContainer = document.getElementById(`${cardId}-chat`);
                const buttonsContainer = document.getElementById(`${cardId}-buttons`);
                const refinementContainer = document.getElementById(`${cardId}-refinement`);
                
                // Hide all card content
                if (chatContainer) chatContainer.style.display = 'none';
                if (buttonsContainer) buttonsContainer.style.display = 'none';
                if (refinementContainer) refinementContainer.style.display = 'none';
                
                // Show only success message
                if (messagesContainer) {
                    messagesContainer.innerHTML = `
                        <div class="message message-success" style="margin-bottom: 1rem;">
                            <span class="message-icon"></span>
                            <span>Configuration accepted and ready for processing.</span>
                        </div>
                    `;
                }
                
                setTimeout(() => createPreviewCard(), 1000);
            }
        }
    ]);
    
    } catch (error) {
        console.error('[REFINE] Error in showRefinementInterface:', error);
        console.error('[REFINE] Error stack:', error.stack);
    }
}

async function submitConfigRefinement(cardId, refinementText) {
    // Add user message
    await addChatMessage(cardId, 'user', refinementText);
    
    // Hide input
    document.getElementById(`${cardId}-refinement`).style.display = 'none';
    
    // Don't hide buttons - let WebSocket completion handle UI cleanup

    // Show thinking indicators
    showThinkingInCard(cardId, 'Analyzing refinement request...', true);
    // Start config-specific dummy progress animation for refinement
    startDummyProgress(cardId, 70000, 'config'); // 70 seconds estimated for refinement
    // Progress routed to card level;

    try {
        const response = await fetch(`${API_BASE}/validate?async=true`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'modifyConfig',
                email: globalState.email,
                session_id: globalState.sessionId,
                instructions: refinementText
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Check if async or sync
            if (data.session_id && data.status === 'processing') {
                // Async - wait for WebSocket
                connectToSession(data.session_id);
                
                // Unregister any existing handlers to prevent duplicates
                unregisterCardHandler(cardId);
                
                registerCardHandler(cardId, ['config'], (wsData, handlerCardId) => {
                    handleConfigWebSocketMessage(wsData, handlerCardId);
                });
            } else if (data.ai_summary) {
                // Sync - show result immediately
                completeThinkingInCard(cardId, 'Refinement complete!');
                // Progress routed to card level;
                globalState.currentConfig = data;
                // Mark Excel file as uploaded since backend handles it during config operations
                globalState.excelFileUploaded = true;
                
                // Skip sync response processing - wait for WebSocket only
            }
        } else {
            completeThinkingInCard(cardId, 'Refinement failed');
            // Progress routed to card level;
            throw new Error(data.error || 'Failed to refine configuration');
        }
    } catch (error) {
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

// New function for post-preview refinement
async function submitConfigRefinementFromPreview(cardId, refinementText) {
    // Add user message
    await addChatMessage(cardId, 'user', refinementText);
    
    // Hide input
    document.getElementById(`${cardId}-refinement`).style.display = 'none';
    
    // Don't hide buttons - let WebSocket completion handle UI cleanup

    // Show thinking indicators
    showThinkingInCard(cardId, 'Analyzing refinement request...', true);
    // Start config-specific dummy progress animation for refinement
    startDummyProgress(cardId, 70000, 'config'); // 70 seconds estimated for refinement
    // Progress routed to card level;

    try {
        const response = await fetch(`${API_BASE}/validate?async=true`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'modifyConfig',
                email: globalState.email,
                session_id: globalState.sessionId,
                instructions: refinementText,
                refinement_mode: 'post_preview' // Indicate this is post-preview refinement
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Check if async or sync
            if (data.session_id && data.status === 'processing') {
                // Async - wait for WebSocket
                connectToSession(data.session_id);
                
                // Unregister any existing handlers to prevent duplicates
                unregisterCardHandler(cardId);
                
                registerCardHandler(cardId, ['refinement'], (wsData, handlerCardId) => {
                    handleRefinementWebSocketMessage(wsData, handlerCardId);
                });
            } else if (data.ai_summary) {
                // Skip sync response processing entirely to prevent duplicates
                // Do not process any sync data - rely only on WebSocket
            }
        } else {
            completeThinkingInCard(cardId, 'Refinement failed');
            // Progress routed to card level;
            throw new Error(data.error || 'Failed to refine configuration');
        }
    } catch (error) {
        if (globalState.cardProgress[cardId]) {
            globalState.cardProgress[cardId].complete('❌ Refinement failed');
            delete globalState.cardProgress[cardId];
        }
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

// New function for refinement with automatic preview generation
async function submitConfigRefinementWithAutoPreview(cardId, refinementText) {
    // Add user message
    await addChatMessage(cardId, 'user', refinementText);
    
    // Hide input
    document.getElementById(`${cardId}-refinement`).style.display = 'none';

    // Show thinking indicators
    showThinkingInCard(cardId, 'Analyzing refinement request...', true);
    startDummyProgress(cardId, 70000, 'config'); // 70 seconds estimated for refinement

    try {
        const response = await fetch(`${API_BASE}/validate?async=true`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                action: 'modifyConfig',
                email: globalState.email,
                session_id: globalState.sessionId,
                instructions: refinementText
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Register WebSocket handler that auto-generates preview
            unregisterCardHandler(cardId);
            registerCardHandler(cardId, ['config'], (wsData, handlerCardId) => {
                handleConfigWebSocketMessageWithAutoPreview(wsData, handlerCardId);
            });
            
            if (data.session_id) {
                connectToSession(data.session_id);
            }
        } else {
            throw new Error(data.error || 'Refinement failed');
        }
    } catch (error) {
        completeThinkingInCard(cardId, 'Refinement failed');
        showMessage(`${cardId}-messages`, `Error: ${error.message}`, 'error');
    }
}

// WebSocket handler that auto-generates preview after config refinement
async function handleConfigWebSocketMessageWithAutoPreview(data, cardId) {
    if (data.type === 'config_generation_complete') {
        completeThinkingInCard(cardId, 'Configuration refined!');

        globalState.currentConfig = data;
        globalState.excelFileUploaded = true;
        globalState.workflowPhase = 'config';

        // Reset balance and cost states since config changed
        globalState.hasInsufficientBalance = false;
        globalState.estimatedCost = null;

        // Save clarifying questions for later use in refinement
        if (data.clarifying_questions) {
            globalState.savedQuestions = data.clarifying_questions;
        }

        let aiMessage = data.ai_summary || data.ai_response || 'Configuration refined successfully!';
        await addChatMessage(cardId, 'ai', aiMessage);

        // Mark config as validated and stored
        globalState.configValidated = true;
        globalState.configStored = true;

        // Auto-trigger preview after refinement (like matches and AI config completion)
        setTimeout(() => {
            createPreviewCard();
        }, 1000);

    } else if (data.type === 'config_generation_failed' || data.error || data.type === 'error') {
        completeThinkingInCard(cardId, 'Refinement failed');
        const errorMessage = data.error || data.message || 'Configuration refinement failed';
        showMessage(`${cardId}-messages`, `Error: ${errorMessage}`, 'error');
    }
}

// WebSocket handler for post-preview refinement
async function handleRefinementWebSocketMessage(data, cardId) {
    if (data.type === 'config_generation_complete') {
        completeThinkingInCard(cardId, 'Refinement complete!');
        // Progress routed to card level

        globalState.currentConfig = data;
        // Mark Excel file as uploaded since backend saves it during config operations
        globalState.excelFileUploaded = true;

        let aiMessage = data.ai_summary || data.ai_response || 'Configuration refined successfully!';

        await addChatMessage(cardId, 'ai', aiMessage, false, 'paragraphs');

        // Add config ID display if available - place it at end of card, not in chat
        if (data.config_id || data.session_id) {
            const card = document.querySelector(`[data-card-id="${cardId}"]`);
            if (card) {
                const configIdDiv = document.createElement('div');
                configIdDiv.className = 'config-success-banner';
                const version = data.config_version || 1;
                const configId = data.config_id || `${data.session_id}_v${version}`;
                configIdDiv.innerHTML = `
                    <div class="message message-success" style="margin: 1rem; margin-top: 0;">
                        <span class="message-icon">✓</span>
                        <span>Configuration refined, code for reuse: <strong>${configId}</strong>, generating preview now...</span>
                    </div>
                `;
                card.appendChild(configIdDiv);
            }
        }

        // Mark config as validated and stored
        globalState.configValidated = true;
        globalState.configStored = true;

        // Auto-trigger preview after refinement (consistent with other flows)
        setTimeout(() => {
            createPreviewCard();
        }, 1000);

    } else if (data.type === 'config_generation_failed') {
        completeThinkingInCard(cardId, 'Refinement failed');
        // Progress routed to card level;
        
        showMessage(`${cardId}-messages`, 
            `Error: ${data.error || 'Configuration refinement failed'}`, 
            'error'
        );
    }
}

// Show actions after refinement (different from initial config actions)
function showRefinementActions(cardId) {
    createButtonRow(`${cardId}-buttons`, [
        {
            text: 'Refine Further',
            icon: '🔧',
            variant: 'secondary',
            width: 1,
            callback: async (e) => {
                const button = e.target.closest('button');
                markButtonSelected(button, '🔧 Refining...');
                // Show refinement input again
                document.getElementById(`${cardId}-refinement`).style.display = 'block';
                const refInput = document.getElementById(`${cardId}-refinement-input`);
                refInput.value = '';
                refInput.focus();
                refInput.onkeydown = (event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        const input = refInput.value.trim();
                        if (!input) {
                            showMessage(`${cardId}-messages`, 'Please enter refinement instructions', 'error');
                            return;
                        }
                        submitConfigRefinementWithAutoPreview(cardId, input);
                    }
                };
                // Update button to submit
                createButtonRow(`${cardId}-buttons`, [
                    {
                        text: 'Submit',
                        variant: 'primary',
                        width: 'full',
                        callback: async (e) => {
                            const button = e.target.closest('button');
                            const input = document.getElementById(`${cardId}-refinement-input`).value.trim();
                            if (!input) {
                                showMessage(`${cardId}-messages`, 'Please enter refinement instructions', 'error');
                                return;
                            }
                            markButtonSelected(button, 'Thinking...');
                            await submitConfigRefinementWithAutoPreview(cardId, input);
                        }
                    }
                ]);
            }
        },
        {
            text: 'Accept & Preview',
            icon: '✅',
            variant: 'primary',
            width: 2,
            callback: async (e) => {
                const button = e.target.closest('button');
                markButtonSelected(button, '✅ Accepted');
                globalState.configValidated = true;
                globalState.configStored = true;
                setTimeout(() => createPreviewCard(), 500);
            }
        }
    ]);
}

// 5. Preview Card - Fixed to ensure consistent card ID and prevent duplicates
