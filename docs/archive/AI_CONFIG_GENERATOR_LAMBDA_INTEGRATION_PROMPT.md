# AI Configuration Generator Lambda Integration

## Context & Objective

You need to integrate the standalone AI Configuration Generator (`ai_config_generator/`) into the existing Perplexity Validator lambda architecture to provide automated configuration generation capabilities through the web interface.

## Current Architecture Analysis

### Local AI Configuration Generator (Source):
- **Location**: `ai_config_generator/` directory
- **Main System**: `ai_config_generator/config_generator_conversational.py`
- **Table Analyzer**: `ai_config_generator/config_generator_step1.py`
- **Enhanced Generator**: `ai_config_generator/config_generator_step2_enhanced.py`
- **Prompt Templates**: `ai_config_generator/prompts/`
- **Test Suite**: `ai_config_generator/test_config_generator.py`

### Existing Lambda Functions:
1. **Validator Lambda** (`src/lambda_function.py`)
   - Claude integration patterns in lines 200-300
   - Schema-based interactions with structured responses
   - Token usage tracking and error handling
   - Deployed via `deployment/create_package.py`

2. **Interface Lambda** (`src/interface_lambda_function.py`)
   - HTTP and WebSocket handler routing
   - Modular action system in `src/interface_lambda/actions/`
   - Real-time progress via `src/interface_lambda/handlers/background_handler.py`
   - Deployed via `deployment/create_interface_package.py`

### Key Integration Points:
- **Web Interface**: `perplexity_validator_interface.html` (lines 500-800 for upload sections)
- **Existing Actions Pattern**: 
  - `src/interface_lambda/actions/process_excel.py` - Excel processing reference
  - `src/interface_lambda/actions/config_validation.py` - config validation integration
  - `src/interface_lambda/actions/diagnostics.py` - progress reporting pattern
- **Core Services**:
  - `src/interface_lambda/core/s3_manager.py` - S3 file operations
  - `src/interface_lambda/core/sqs_service.py` - background processing
  - `src/interface_lambda/core/validator_invoker.py` - validator lambda calls
- **WebSocket Support**: `src/interface_lambda/handlers/background_handler.py`

## Integration Requirements

### 1. Web Interface Updates (`perplexity_validator_interface.html`)
**Add Configuration Generation Section:**
```html
<!-- New section after existing upload areas -->
<div class="upload-section">
    <h3>🤖 AI Configuration Generator</h3>
    <p>Generate optimized validation configurations automatically from your Excel data.</p>
    
    <div class="upload-area" id="config-gen-drop-zone">
        <p>📋 Drop Excel file here or click to browse</p>
        <input type="file" id="excel-file-input" accept=".xlsx,.xls" hidden>
    </div>
    
    <div class="generation-options" id="generation-options" style="display:none;">
        <h4>Generation Settings</h4>
        <label>
            <input type="radio" name="generation-mode" value="automatic" checked> 
            Automatic Generation (recommended)
        </label>
        <label>
            <input type="radio" name="generation-mode" value="interview"> 
            Interactive Interview Mode
        </label>
        <button id="generate-config-btn" class="action-btn">Generate Configuration</button>
    </div>
    
    <div id="config-generation-progress" style="display:none;">
        <div class="progress-container">
            <div class="progress-bar" id="config-gen-progress"></div>
        </div>
        <div id="config-gen-status">Analyzing table structure...</div>
    </div>
</div>
```

**JavaScript Integration:**
- Add event handlers for file upload and generation
- WebSocket listeners for real-time progress updates
- Download generated configuration files
- Optional: Interview mode with sequential Q&A interface

### 2. New Interface Lambda Action (`src/interface_lambda/actions/generate_config.py`)

**Core Requirements:**
```python
async def handle_generate_config(event_data, websocket_callback=None):
    """
    Generate configuration from uploaded Excel file
    
    Args:
        event_data: {
            'excel_s3_key': 'path/to/uploaded.xlsx',
            'generation_mode': 'automatic' | 'interview',
            'conversation_id': 'optional for interview mode',
            'user_message': 'optional for interview continuation'
        }
    
    Returns:
        {
            'success': True,
            'config_s3_key': 'path/to/generated_config.json',
            'conversation_id': 'conv_12345678' if interview mode,
            'ai_response': 'Generated response text',
            'download_url': 'presigned S3 URL',
            'metadata': {...}
        }
    """
```

**Integration Steps:**
1. **Copy AI Config Generator Components to Interface Lambda:**
   ```python
   # Copy from local ai_config_generator/ to interface lambda package
   # Source files to copy:
   # - ai_config_generator/config_generator_conversational.py
   # - ai_config_generator/config_generator_step1.py  
   # - ai_config_generator/config_generator_step2_enhanced.py
   # - ai_config_generator/prompts/
   
   # Import in new action:
   from config_generator_conversational import ConversationalConfigSystem
   from config_generator_step1 import TableAnalyzer
   ```

2. **Excel File Processing (Follow `src/interface_lambda/actions/process_excel.py` patterns):**
   - Download Excel file from S3 using `src/interface_lambda/core/s3_manager.py`
   - Use `TableAnalyzer` from local `ai_config_generator/config_generator_step1.py`
   - Generate table analysis JSON similar to existing Excel processing

3. **Configuration Generation (Adapt Claude patterns from `src/lambda_function.py`):**
   - Initialize `ConversationalConfigSystem` with Claude API key from environment
   - Use existing Claude interaction patterns from validator lambda (lines 200-300)
   - For automatic mode: Generate config with optimized prompt
   - For interview mode: Start or continue conversation using conversation state
   - Apply real-time validation using existing `src/interface_lambda/actions/config_validation.py`

4. **S3 Upload & Response (Follow `src/interface_lambda/core/s3_manager.py` patterns):**
   - Upload generated config to S3 with versioned naming (similar to existing file handling)
   - Generate presigned download URL using existing S3 methods
   - Return structured response with metadata following existing action response patterns

### 3. WebSocket Progress Updates

**Progress Events to Send:**
```python
progress_events = [
    "📊 Analyzing Excel file structure...",
    "🧠 Detecting data domain and patterns...", 
    "⚙️ Generating optimal configuration...",
    "🤖 Applying AI optimization strategies...",
    "✅ Validating generated configuration...",
    "💾 Saving configuration file...",
    "🎉 Configuration generation complete!"
]
```

**WebSocket Integration (Follow `src/interface_lambda/handlers/background_handler.py` patterns):**
- Use existing WebSocket infrastructure in interface lambda
- Follow progress update patterns from `src/interface_lambda/actions/diagnostics.py`
- Send progress updates during each generation step
- Include token usage and performance metrics (following validator lambda patterns)
- Handle conversation state for interview mode using existing state management

### 4. Deployment Integration

**Update `deployment/create_interface_package.py` (around line 150-200 where files are copied):**
```python
# Add AI config generator files to interface package (after existing file copies)
ai_config_files = [
    ('ai_config_generator/config_generator_conversational.py', ''),
    ('ai_config_generator/config_generator_step1.py', ''), 
    ('ai_config_generator/config_generator_step2_enhanced.py', ''),
    ('ai_config_generator/prompts/conversational_interview_prompt.md', 'prompts/'),
    ('ai_config_generator/prompts/generate_column_config_prompt.md', 'prompts/'),
]

# Add to existing package creation process (follow existing patterns)
for src_file, dest_subdir in ai_config_files:
    if os.path.exists(src_file):
        dest_dir = os.path.join(temp_package_dir, dest_subdir)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src_file, dest_dir)
        print(f"Added {src_file} to interface package")
```

**Environment Variables:**
- `ANTHROPIC_API_KEY` - Claude API key for config generation
- `CONFIG_GENERATION_ENABLED` - Feature flag for enabling/disabling

**Dependencies:**
- Add `aiohttp` to `deployment/requirements-interface-lambda.txt` (if not already present)
- Ensure `pandas` available for Excel analysis (likely already in requirements)
- Check `deployment/requirements-lambda.txt` for Claude API dependencies

### 5. Interview Mode Implementation

**Conversation Management:**
- Store conversation state in DynamoDB (reuse existing tables)
- Track conversation ID, messages, and generated configs
- Support multi-turn Q&A with context preservation

**Interview UI Flow:**
1. User uploads Excel file
2. System analyzes and generates 3-7 domain-specific questions
3. User answers questions through chat interface
4. System applies optimizations and generates config
5. User can continue conversation for further refinements

## Implementation Priority

### Phase 1: Basic Integration
1. ✅ Add `generate_config.py` action to interface lambda
2. ✅ Integrate automatic config generation mode
3. ✅ Add basic web interface with file upload
4. ✅ WebSocket progress updates
5. ✅ S3 file management and download

### Phase 2: Interview Mode
1. ✅ Conversation state management
2. ✅ Interactive Q&A interface
3. ✅ Multi-turn conversation support
4. ✅ Real-time config refinement

### Phase 3: Advanced Features
1. ✅ Configuration comparison tools
2. ✅ Batch processing for multiple files
3. ✅ Template management and reuse
4. ✅ Analytics and usage tracking

## Technical Considerations

### Error Handling:
- Graceful degradation when AI service unavailable
- File format validation and error messages
- Rate limiting and API quota management
- Conversation timeout and cleanup

### Security:
- API key management through environment variables
- S3 access controls for generated files
- Input validation for Excel files and user messages
- Conversation isolation between users

### Performance:
- Async processing for large Excel files
- Caching of table analysis results
- Optimized model selection (sonar-pro vs claude-sonnet-4-0)
- Progress tracking for long-running operations

### Monitoring:
- CloudWatch metrics for generation success/failure rates
- Token usage tracking and cost monitoring
- Performance metrics (generation time, file sizes)
- User interaction analytics

## Expected Outcomes

After integration, users will be able to:
1. **Upload Excel file** through existing web interface
2. **Generate configuration automatically** with AI optimization
3. **Interact with AI** through interview mode for custom requirements
4. **Download optimized configs** ready for immediate use
5. **Track progress** in real-time through WebSocket updates
6. **Validate configs** using existing validation infrastructure

The integration leverages your existing robust lambda architecture while adding powerful AI-driven configuration generation capabilities that seamlessly fit into the current user workflow.

## File Reference Map

### Source Files (Local AI Config Generator):
```
ai_config_generator/
├── config_generator_conversational.py     → Copy to interface lambda package
├── config_generator_step1.py              → Copy to interface lambda package  
├── config_generator_step2_enhanced.py     → Copy to interface lambda package
├── prompts/
│   ├── conversational_interview_prompt.md → Copy to interface lambda prompts/
│   └── generate_column_config_prompt.md   → Copy to interface lambda prompts/
├── README.md                              → Reference for integration details
└── test_config_generator.py               → Use for testing patterns
```

### Target Files (Existing Lambda Architecture):
```
src/
├── lambda_function.py                     → Reference Claude patterns (lines 200-300)
├── interface_lambda_function.py           → Main entry point for new action
├── interface_lambda/
│   ├── actions/
│   │   ├── process_excel.py               → Pattern for Excel processing
│   │   ├── config_validation.py           → Integration point for validation
│   │   ├── diagnostics.py                 → Pattern for progress updates
│   │   └── generate_config.py             → NEW FILE TO CREATE
│   ├── core/
│   │   ├── s3_manager.py                  → File upload/download patterns
│   │   ├── sqs_service.py                 → Background processing patterns
│   │   └── validator_invoker.py           → Lambda invocation patterns
│   └── handlers/
│       └── background_handler.py          → WebSocket progress patterns
├── perplexity_validator_interface.html    → Add UI section (lines 500-800)
└── deployment/
    ├── create_interface_package.py        → Update with AI config files
    ├── requirements-interface-lambda.txt  → Add dependencies
    └── requirements-lambda.txt            → Check existing dependencies
```

## Next Steps

1. **Review existing lambda architecture** in `src/interface_lambda/actions/process_excel.py`
2. **Study Claude integration patterns** in `src/lambda_function.py` (lines 200-300)
3. **Implement `src/interface_lambda/actions/generate_config.py`** following existing action patterns
4. **Update `perplexity_validator_interface.html`** with new configuration generation UI (after line 800)
5. **Modify `deployment/create_interface_package.py`** to include AI config generator files
6. **Test integration** with existing deployment scripts
7. **Deploy and validate** end-to-end functionality

This integration will transform the Perplexity Validator from a validation-only tool into a complete configuration lifecycle management platform with AI-powered automation.