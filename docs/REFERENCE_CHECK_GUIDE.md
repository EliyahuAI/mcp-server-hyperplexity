# ✅ Reference Check App - FINAL Implementation

**Branch**: `reference-check-app`
**Date**: 2025-11-07
**Status**: 100% Complete - Validation Flow + PDF Upload Integrated

---

## 🎯 What It Does Now

The Reference Check app works like **table_maker with validation**:

1. **User submits text** with claims and citations (paste text OR upload PDF)
2. **PDF conversion** (optional): Lightweight markdown conversion using pymupdf4llm
3. **Claims extracted** by SONNET 4.5
4. **Table generated** with:
   - **ID columns populated**: Claim ID, Statement, Context, Reference
   - **RESEARCH columns empty**: Support Level, Confidence, Validation Notes
5. **Static validation config copied** to session
6. **Preview auto-triggered** (like table_maker)
7. **User runs validation** to fill RESEARCH columns

---

## 🚀 Two Access Modes

### Mode 1: Default (Get Started Card)
**URL**: `https://hyperplexity.ai` or `https://hyperplexity.ai/?mode=default`

After email validation:
- Shows Get Started card with 3 options:
  - 📁 Upload Your Own Table
  - ✨ Create New Table
  - 🔍 Check References

User clicks "Check References" → goes to Reference Check card

### Mode 2: Direct Access (Page Detection)
**URL**: `https://hyperplexity.ai/?mode=reference-check`

After email validation:
- **Bypasses Get Started card**
- **Goes straight to Reference Check card**
- Optimized for users who only want reference checking

---

## 📋 Complete User Flow

### Step 1: Access & Email Validation
```
User → URL (with or without ?mode=reference-check)
  ↓
Email validation
  ↓
Page detection checks mode:
  - Default → Get Started card (3 options)
  - reference-check → Reference Check card directly
```

### Step 2: Submit Text (Two Options)

**Option A: Paste Text**
```
Reference Check Card
  ↓
User pastes text with citations into textarea
  ↓
[Optional] Frontend validates length (96K chars max)
  ↓
Backend validates size (32K tokens max)
  ↓
[If too large] Error returned immediately
  ↓
[If valid] Processing starts
```

**Option B: Upload PDF**
```
Reference Check Card
  ↓
User clicks "Upload PDF" button
  ↓
User selects PDF file
  ↓
[Frontend validates file size: 50MB max]
  ↓
[If too large] Error shown immediately (no upload)
  ↓
[If valid] Frontend requests presigned URL (small JSON request)
  ↓
Backend generates presigned S3 URL (returns in <1 second)
  ↓
Frontend uploads PDF directly to S3 (bypasses API Gateway/Lambda limits)
  ↓
Frontend confirms upload complete
  ↓
Backend queues conversion to SQS (returns immediately)
  ↓
Background processor converts PDF to text using PyMuPDF
  ↓
Conversion result sent via WebSocket
  ↓
Reference check auto-triggered with converted text
  ↓
Results delivered via WebSocket
```

### Step 3: Claim Extraction
```
Progress indicator shows: "Extracting claims and references. This takes a minute..." (50%)
  ↓
SONNET 4.5 extracts:
  - Discrete claims
  - Context for each claim
  - Cited references
  - Reference details (authors, year, DOI, etc.)
  - Text locations (for future highlighting)
```

### Step 4: Table Generation
```
Backend generates:
  - session_id (if not provided)
  - CSV with structure:
    • Claim ID [POPULATED]
    • Statement [POPULATED]
    • Context [POPULATED]
    • Reference [POPULATED]
    • Support Level [EMPTY]
    • Confidence [EMPTY]
    • Validation Notes [EMPTY]

Saves to: results/{domain}/{email_prefix}/{session_id}/reference_check_{conversation_id}.csv
```

### Step 5: Config Copy & Dynamic QC
```
Static validation config loaded from:
  src/lambdas/interface/actions/reference_check/reference_check_validation_config.json

Dynamic QC Decision:
  - Check if ANY claims have Supporting Data
  - If YES: Set enable_qc = true (paper's own results need critical assessment)
  - If NO: Keep enable_qc = false (external references can be directly verified)

Config updated with:
  - session_id
  - email
  - timestamp
  - qc_dynamically_enabled (true/false)

Saved to:
  results/{domain}/{email_prefix}/{session_id}/reference_check_validation_config.json
```

### Step 6: Auto-Preview
```
Frontend receives:
  - csv_s3_key
  - config_s3_key
  - session_id
  - summary stats

Frontend:
  - Stores in globalState
  - Sets flags (configValidated=true, configStored=true, excelFileUploaded=true)
  - Calls createPreviewCard()

User sees:
  - Table structure preview
  - ID columns filled
  - RESEARCH columns empty
  - "Process Table" button
```

### Step 7: User Runs Validation
```
User clicks "Process Table"
  ↓
Standard validation flow (like table_maker):
  - HAIKU 4.5 with 3 web searches per claim
  - Fills Support Level, Confidence, Validation Notes
  - Uses static config for validation rules
  ↓
Results delivered via WebSocket
  ↓
User downloads completed table
```

---

## 🔧 Technical Implementation

### Frontend Components

**PDF Upload** (frontend line ~12706-12853):
```javascript
// Upload button and file input
<div style="margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem;">
    <input type="file" id="${cardId}-pdf-input" accept=".pdf" style="display: none;">
    <button id="${cardId}-pdf-upload-btn" class="btn-secondary">
        Upload PDF
    </button>
    <span id="${cardId}-pdf-status"></span>
</div>

// Handle PDF upload
async function handlePdfUpload(cardId, file) {
    // Create FormData (following Excel upload pattern)
    const formData = new FormData();
    formData.append('pdf_file', file);
    formData.append('action', 'convertPdfToMarkdown');

    // Upload and convert (synchronous)
    const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData
    });

    const data = await response.json();

    if (data.success && data.markdown_text) {
        // Populate textarea with markdown
        textarea.value = data.markdown_text;

        // Show success status
        pdfStatus.textContent = `[SUCCESS] Converted ${data.page_count} pages`;
    }
}
```

**Page Detection** (frontend line ~2568):
```javascript
function detectPageType() {
    // Check URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'reference-check' ||
        urlParams.get('page') === 'reference-check') {
        return 'reference-check';
    }

    // Check page title
    if (document.title.toLowerCase().includes('reference check')) {
        return 'reference-check';
    }

    // Check URL path
    if (window.location.pathname.includes('reference-check')) {
        return 'reference-check';
    }

    return 'default';
}
```

**Modified Email Validation** (frontend line ~6909):
```javascript
function handleEmailValidated(cardId) {
    localStorage.setItem('validatedEmail', globalState.email);

    // ... card UI updates ...

    setTimeout(() => {
        const pageType = detectPageType();

        if (pageType === 'reference-check') {
            // Direct to Reference Check card
            console.log('[PAGE DETECT] Reference-check mode detected, going straight to card');
            createReferenceCheckCard();
        } else if (globalState.isNewUser) {
            // Default: show Get Started options
            createUploadOrDemoCard();
        } else {
            createUploadCard();
        }
    }, 500);
}
```

**Auto-Preview Trigger** (frontend line ~12823):
```javascript
function handleReferenceCheckComplete(data) {
    const cardId = referenceCheckState.cardId;
    const { csv_s3_key, config_s3_key, session_id, summary } = data;

    // Store in globalState (like table_maker)
    globalState.sessionId = session_id;
    globalState.configValidated = true;
    globalState.configStored = true;
    globalState.excelFileUploaded = true;

    // Complete thinking indicator
    completeThinkingInCard(cardId);

    // Show summary message
    const message = `Reference check complete! Found ${summary.total_claims} claims...`;
    showMessage(`${cardId}-messages`, message, 'success');

    // Auto-trigger preview (like table_maker)
    setTimeout(() => {
        createPreviewCard();
    }, 1000);
}
```

### Backend Components

**Presigned URL Upload** (presigned_upload.py - NEW):
```python
# Max file size: 50MB for both PDFs and Excel (no API Gateway/Lambda limits!)
MAX_PDF_SIZE = 50 * 1024 * 1024
MAX_EXCEL_SIZE = 50 * 1024 * 1024

def request_presigned_url(request_data: Dict[str, Any], context: Any):
    """
    Generate presigned S3 URL for direct browser-to-S3 upload.

    Flow:
    1. Frontend sends small JSON request (file metadata only)
    2. Backend generates presigned URL (valid for 5 minutes)
    3. Frontend uploads file directly to S3 using presigned URL
    4. Frontend confirms upload complete
    5. Backend queues processing (PDF conversion or Excel analysis)

    Advantages:
    - No API Gateway 10MB payload limit
    - No Lambda 6MB invocation limit
    - Supports files up to 50MB (or more if needed)
    - Faster uploads (direct to S3)
    - Lower costs (no Lambda payload processing)
    """

def confirm_upload_complete(request_data: Dict[str, Any], context: Any):
    """
    Verify file in S3 and queue processing.

    For PDFs: Queue to SQS for background conversion
    For Excel: Confirm upload success (processing triggered separately)
    """
```

**PDF Conversion** (pdf_converter.py):
```python
async def handle_pdf_conversion(request_data: Dict[str, Any], context: Any):
    """
    Background PDF conversion processor (triggered by SQS).
    Downloads PDF from S3, converts to text, auto-triggers reference check.
    """
```

**HTTP Handler Routing** (http_handler.py line ~71):
```python
# Check for PDF conversion action
if form_data.get('action') == 'convertPdfToMarkdown':
    pdf_converter = lazy_import('interface_lambda.actions.reference_check', 'pdf_converter')
    return pdf_converter.handle_pdf_multipart(files, form_data, context)
```

**Session Generation** (conversation.py line ~111):
```python
# Generate session ID if not provided (like table_maker does)
if not session_id:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    random_hex = uuid.uuid4().hex[:8]
    session_id = f"session_{timestamp}_{random_hex}"
    logger.info(f"[REFERENCE_CHECK] Generated new session ID: {session_id}")
```

**CSV & Config Save** (execution.py line ~870):
```python
# Save CSV to session results folder (like table_maker does)
domain = email.split('@')[1] if '@' in email else 'unknown'
email_prefix = email.split('@')[0] if '@' in email else email
csv_filename = f"reference_check_{conversation_id}.csv"
csv_s3_key = f"results/{domain}/{email_prefix}/{session_id}/{csv_filename}"

storage_manager.s3_client.put_object(
    Bucket=storage_manager.bucket_name,
    Key=csv_s3_key,
    Body=csv_content,
    ContentType='text/csv'
)

# Load static validation config from local file only (no S3 caching)
config_path = Path(__file__).parent / 'reference_check_validation_config.json'
with open(config_path, 'r') as f:
    validation_config = json.load(f)

# Update config metadata
validation_config['storage_metadata']['session_id'] = session_id
validation_config['storage_metadata']['email'] = email
validation_config['storage_metadata']['copied_at'] = datetime.now().isoformat()

# Save to session
config_filename = f"reference_check_validation_config.json"
config_s3_key = f"results/{domain}/{email_prefix}/{session_id}/{config_filename}"

storage_manager.s3_client.put_object(
    Bucket=storage_manager.bucket_name,
    Key=config_s3_key,
    Body=json.dumps(validation_config, indent=2),
    ContentType='application/json'
)
```

**WebSocket Completion** (execution.py line ~950):
```python
websocket_client.send_to_session(session_id, {
    'type': 'reference_check_complete',
    'conversation_id': conversation_id,
    'status': 'complete',
    'csv_s3_key': result['csv_s3_key'],
    'csv_filename': result['csv_filename'],
    'config_s3_key': result['config_s3_key'],
    'session_id': session_id,
    'summary': result['summary']
})
```

### Static Validation Config

**File**: `reference_check_validation_config.json` (137 lines)

**ID Columns** (already populated):
- Claim ID - Unique identifier
- Statement - The factual claim
- Context - Surrounding text
- Reference - Citation/source

**RESEARCH Columns** (to be filled via validation):
- Support Level - 6-level assessment (strongly_supported → inaccessible)
- Confidence - 0.0-1.0 score
- Validation Notes - Detailed explanation

**Search Groups**:
- Group 0: Claim Identifiers (no web search needed)
- Group 1: Reference Validation (with 3 web searches)

**Model Configuration**:
- Default: claude-haiku-4-5
- Max web searches: 3
- QC disabled (not needed for validation)

---

## 📊 File Structure

```
results/{domain}/{email_prefix}/{session_id}/
├── reference_check_{conversation_id}.csv          [ID columns filled, RESEARCH empty]
└── reference_check_validation_config.json         [Static config with session metadata]

reference_checks/{email}/{session_id}/{conversation_id}/
└── conversation_state.json                         [Processing state]
```

---

## 🎭 Comparison: Before vs After

### Before (Download-Only Flow)
```
User submits text
  ↓
Claims extracted
  ↓
Claims validated (HAIKU + web search)
  ↓
CSV generated (all columns filled)
  ↓
User downloads CSV
  ✗ No preview
  ✗ No validation control
  ✗ No session tracking
```

### After (Validation Flow)
```
User submits text
  ↓
Claims extracted
  ↓
CSV generated (ID columns filled, RESEARCH empty)
  ↓
Static config copied to session
  ↓
Preview auto-triggered
  ↓
User sees table structure
  ↓
User runs validation (fills RESEARCH columns)
  ↓
User downloads completed table
  ✓ Full preview
  ✓ User controls validation
  ✓ Session tracking
  ✓ Consistent with table_maker
```

---

## 📝 Testing Checklist

### Test 1: Direct Mode Access
- [ ] Access `?mode=reference-check`
- [ ] Verify bypasses Get Started card
- [ ] Verify goes straight to Reference Check card

### Test 2: Default Mode Access
- [ ] Access without mode parameter
- [ ] Verify shows Get Started card
- [ ] Verify "Check References" button works

### Test 3: PDF Upload Flow
- [ ] Click "Upload PDF" button
- [ ] Select a PDF file with citations
- [ ] Verify "Converting PDF..." status appears
- [ ] Verify markdown text populates textarea
- [ ] Verify page count shown in success message
- [ ] Verify textarea is editable after conversion
- [ ] Submit converted text for reference checking

### Test 4: Full Validation Flow
- [ ] Submit text with citations (paste or PDF)
- [ ] Verify claims extracted
- [ ] Verify CSV created with ID columns filled
- [ ] Verify config copied to session
- [ ] Verify preview auto-triggers
- [ ] Verify RESEARCH columns empty in preview
- [ ] Run validation
- [ ] Verify RESEARCH columns filled
- [ ] Download and verify final CSV

### Test 5: Text Size Limits
- [ ] Submit text > 24K words
- [ ] Verify immediate error response
- [ ] Verify no session created
- [ ] Verify no cost incurred

### Test 6: Session Tracking
- [ ] Check S3 for session folder structure
- [ ] Verify CSV saved to results/{domain}/{email_prefix}/{session_id}/
- [ ] Verify config saved to same location
- [ ] Verify config has correct metadata

---

## 💰 Cost Breakdown

**File Upload** (PDF or Excel):
- Max file size: **50MB** (using S3 presigned URLs - no API Gateway/Lambda limits!)
- Direct browser-to-S3 upload (fast, efficient)
- No Lambda payload processing costs

**PDF Conversion** (optional):
- Background processing using PyMuPDF (fast text extraction)
- No API calls, no cost
- ~1-5 seconds per document

**Claim Extraction** (once):
- SONNET 4.5, no web search
- ~$0.02-0.05 per extraction

**Validation** (when user clicks "Process Table"):
- HAIKU 4.5 with 3 web searches per claim
- ~$0.01-0.03 per claim
- For 10 claims: ~$0.10-0.30
- For 25 claims: ~$0.25-0.75

**Total for 10 claims**: ~$0.12-0.35
**Total for 25 claims**: ~$0.27-0.80

---

## 🚢 Deployment

```bash
# From project root
./deploy_interface.sh
```

This deploys:
- Updated frontend with page detection and PDF upload
- Updated conversation.py with session generation
- Updated execution.py with config copying
- New static validation config
- PDF converter module (pdf_converter.py)
- New dependency: pymupdf4llm>=0.0.5

**Dependencies Added:**
- `pymupdf4llm>=0.0.5` - LLM-optimized PDF to markdown conversion
- Uses existing `PyMuPDF>=1.24.0` for PDF processing

---

## 📚 Related Documentation

- **Design**: `docs/REFERENCE_CHECK_DESIGN.md`
- **Implementation Status**: `docs/REFERENCE_CHECK_IMPLEMENTATION_STATUS.md`
- **This Guide**: `REFERENCE_CHECK_FINAL.md`

---

## ✨ Key Benefits

1. **Consistent UX**: Matches table_maker flow
2. **User Control**: Preview before validation
3. **Session Tracking**: Full S3/DynamoDB integration
4. **Cost Optimization**: Only validate when user approves
5. **Page Detection**: Direct access for power users
6. **Static Config**: Always loads from deployed local file (no S3 caching)
7. **Pre-filled Tables**: Users see extracted data immediately
8. **PDF Support**: Lightweight markdown conversion with pymupdf4llm
9. **Flexible Input**: Paste text OR upload PDF - user's choice
10. **Dynamic QC**: Automatically enables QC when claims have Supporting Data (paper's own results need critical assessment)

---

**Status**: ✅ Ready for deployment and testing!
