# Reference Check App - Design Document

**Version:** 1.0
**Created:** 2025-11-06
**Status:** Design Phase

---

## Table of Contents
1. [Overview](#overview)
2. [User Flow](#user-flow)
3. [Architecture](#architecture)
4. [Data Model](#data-model)
5. [Backend Components](#backend-components)
6. [Frontend Components](#frontend-components)
7. [API Specification](#api-specification)
8. [WebSocket Messages](#websocket-messages)
9. [Implementation Phases](#implementation-phases)

---

## Overview

### Purpose
The Reference Check app validates claims and statements in AI-generated content or scientific literature by:
1. Extracting statements/claims with their context
2. Identifying references cited for each claim
3. Validating what each reference actually says
4. Assessing support level (supported/contradicted/unclear/inaccessible)

### Key Features
- **Auto-triggered workflow**: User submits text → automatic extraction → automatic preview
- **Smart extraction**: SONNET 4.5 identifies claims, context, and references
- **Reference validation**: For cited references, checks what they actually say
- **Fact-checking**: For uncited claims, runs general fact-check
- **Nuanced assessment**: 5-6 level support scale (not just true/false)
- **Early return**: If text is unsuitable, explains why and continues conversation
- **Text mapping** (future): Map back to original text location

---

## User Flow

### Entry Point
1. After email verification, user sees modified "Get Started" card
2. Three options:
   - Upload Your Own Table (existing)
   - **Check References** (NEW)
   - Create New Table (existing)

### Simplified Flow
```
User selects "Check References"
    ↓
Reference Check Card appears
    ↓
User pastes text (AI output or scientific paper with references)
    ↓
User clicks "Check References"
    ↓
[Upfront validation]
  - Word/token count check
  - Max: ~32K tokens (~24K words at 1.33 tokens/word)
  - Return error immediately if too large
    ↓
[Automatic processing - no configuration needed]
    ↓
SONNET 4.5 extracts:
  - Statements/claims
  - Context for each
  - References (if present)
    ↓
For each claim:
  - If has reference → validate against reference
  - If no reference → fact-check the statement
    ↓
Preview automatically triggers (no button click)
    ↓
Preview shows table with:
  - Statement
  - Context
  - Reference (if present)
  - What reference says
  - Support level
    ↓
User can:
  - Accept → Download as CSV
  - Refine → Provide feedback and re-run
```

### Edge Cases
- **Text too large**: Return error immediately (max 32K tokens / ~24K words)
- **Unsuitable text**: SONNET returns early with explanation, continues conversation
- **No references found**: All claims get fact-checked instead
- **Mixed content**: Some claims have references, others don't (hybrid approach)
- **Reference inaccessible**: Support level = "inaccessible"

---

## Architecture

### Pattern: Modeled after Table Maker

```
Frontend (HTML/JS)
    ↓
API Gateway (POST /validate)
    ↓
Interface Lambda (http_handler.py)
    ↓
Reference Check Action Router
    ↓
SQS Queue (async processing)
    ↓
Background Handler
    ↓
Reference Check Pipeline
    ↓
WebSocket Updates → Frontend
```

### Pipeline Steps

```
Step 0: Text Analysis & Claim Extraction (30-60s)
  - SONNET 4.5 analyzes text
  - Extracts claims with context and references
  - Determines if text is suitable
  - Early return if unsuitable

Step 1: Reference Validation (60-120s)
  - For each claim with reference:
    → Fetch reference content
    → Ask: "What does this reference say about X?"
    → Rate support level
  - For each claim without reference:
    → General fact-check query
    → Rate reliability
  - Parallel processing where possible

Step 2: Generate Results Table
  - Compile all validation results
  - Generate CSV with columns:
    • Statement/Claim
    • Context
    • Reference (if present)
    • Reference Description
    • What Reference Says
    • Support Level
  - Auto-trigger preview
```

---

## Data Model

### Conversation State
```python
{
    'conversation_id': str,           # Unique ID for this check
    'session_id': str,                # User session
    'email': str,                     # User email
    'created_at': ISO timestamp,
    'last_updated': ISO timestamp,
    'status': str,                    # 'analyzing' | 'validating' | 'complete' | 'failed'
    'turn_count': int,                # Number of conversation turns
    'run_key': str,                   # DynamoDB run record key
    'submitted_text': str,            # Original text from user
    'text_length': int,               # Character count
    'extraction_result': dict,        # Step 0 output
    'validation_results': list,       # Step 1 output
    'csv_s3_key': str,               # Step 2 output
}
```

### Extraction Result (Step 0)
```python
{
    'is_suitable': bool,                # Can we process this text?
    'reason': str,                      # If not suitable, why?
    'continue_conversation': bool,      # Should we ask user for clarification?
    'claims': [
        {
            'claim_id': str,            # Unique ID (claim_001, claim_002, etc.)
            'statement': str,           # The actual claim/statement
            'context': str,             # Surrounding context
            'reference': str | null,    # Citation (e.g., "[Smith et al., 2024]")
            'reference_details': {      # Parsed reference info
                'authors': list,
                'year': str,
                'title': str,
                'doi': str | null,
                'url': str | null
            } | null,
            'text_location': {          # For future text mapping
                'start_char': int,
                'end_char': int,
                'paragraph_index': int
            }
        }
    ],
    'total_claims': int,
    'claims_with_references': int,
    'claims_without_references': int
}
```

### Validation Result (Step 1)
```python
{
    'claim_id': str,
    'statement': str,
    'context': str,
    'reference': str | null,
    'reference_description': str,      # What is this source?
    'reference_says': str,              # What does it say about the claim?
    'support_level': str,               # One of the support levels
    'confidence': float,                # 0-1 confidence in assessment
    'validation_notes': str,            # Additional context
    'accessible': bool,                 # Could we access the reference?
    'validation_timestamp': ISO timestamp
}
```

### Support Levels (6 levels)
```python
SUPPORT_LEVELS = {
    'strongly_supported': 'Strongly Supported - Reference directly confirms the claim',
    'supported': 'Supported - Reference generally agrees with the claim',
    'partially_supported': 'Partially Supported - Reference supports some aspects',
    'unclear': 'Unclear - Reference is ambiguous or insufficient',
    'contradicted': 'Contradicted - Reference disagrees with the claim',
    'inaccessible': 'Inaccessible - Could not access the reference'
}
```

---

## Backend Components

### File Structure
```
/src/lambdas/interface/actions/reference_check/
├── __init__.py                    # Action routing
├── conversation.py                # Conversation management
├── execution.py                   # Pipeline orchestration
├── preview.py                     # Preview generation
├── reference_check_config.json   # Configuration
├── prompts/
│   ├── claim_extraction.md       # Step 0 prompt
│   └── reference_validation.md   # Step 1 prompt
└── reference_check_lib/
    ├── claim_extractor.py        # Extract claims from text
    ├── reference_validator.py    # Validate references
    ├── fact_checker.py           # Fact-check uncited claims
    └── result_compiler.py        # Compile final results
```

### Key Functions

#### conversation.py
```python
async def handle_reference_check_start_async(request_data, context):
    """HTTP endpoint → SQS queue"""
    # 1. Validate email/session
    # 2. Validate text size (max 32K tokens / ~24K words)
    # 3. Return error if too large
    # 4. Generate conversation_id
    # 5. Queue to SQS
    # 6. Return 200 immediately

def _validate_text_size(text):
    """
    Check if text is within token limits
    - Count words
    - Estimate tokens: words * 1.33 (conservative: 4 tokens per 3 words)
    - Max: 32,000 tokens (~24,000 words)
    - Return (is_valid: bool, word_count: int, estimated_tokens: int)
    """

async def handle_reference_check_start(request_data, context):
    """Background processor → WebSocket updates"""
    # 1. Create run record
    # 2. Save submitted text
    # 3. Trigger execution pipeline
    # 4. Send progress updates
```

#### execution.py
```python
async def execute_reference_check(email, session_id, conversation_id, run_key):
    """
    Main pipeline orchestrator

    Step 0: Extract claims
    - Call claim_extractor
    - Check if suitable
    - Early return if not suitable
    - Send WebSocket update with claims found

    Step 1: Validate claims
    - For each claim: validate reference or fact-check
    - Parallel processing where possible
    - Send progress updates per claim

    Step 2: Compile results
    - Generate CSV
    - Save to S3
    - Auto-trigger preview
    - Send completion message
    """

async def _extract_claims(submitted_text, conversation_id):
    """Extract claims using SONNET 4.5"""
    pass

async def _validate_claim(claim, conversation_id):
    """Validate single claim (reference or fact-check)"""
    pass

async def _compile_results(validation_results, conversation_id):
    """Compile final CSV"""
    pass
```

---

## Frontend Components

### Modified Get Started Card

**Location**: `frontend/perplexity_validator_interface2.html` (Lines ~6950-6985)

**Changes**:
```javascript
// Add third button between "Upload Table" and "Create New Table"
{
    text: 'Check References',
    class: 'quaternary',  // Cyan color
    callback: () => proceedWithReferenceCheck()
}
```

### New Reference Check Card

**New Function**: `createReferenceCheckCard()` (after line 11947)

```javascript
function createReferenceCheckCard() {
    const cardId = generateCardId();
    referenceCheckState.cardId = cardId;

    return createCard({
        id: cardId,
        icon: '🔍',  // Magnifying glass
        title: 'Reference Check',
        subtitle: 'Verify AI output or literature with citations',
        content: `
            <div class="form-group" style="width: 100%;">
                <label>
                    Drop in the text you'd like verified — AI output or scientific literature (include references)
                </label>
                <textarea id="reference-text-input-${cardId}"
                          class="form-input"
                          placeholder="Paste your text here. Include any references or citations if present.

Example:
Studies show that AI models can hallucinate facts [1]. Recent research indicates this happens in about 15-20% of responses [2]. However, newer models show improvement [Smith et al., 2024].

References:
[1] Johnson, A. (2023). Understanding AI Hallucinations. Nature AI.
[2] Chen, L. et al. (2024). Measuring Factual Accuracy. arXiv:2401.12345"
                          rows="12"
                          style="width: 100%; font-family: monospace; font-size: 14px;"></textarea>
                <div style="margin-top: 0.5rem; font-size: 12px; color: #666;">
                    Tip: Include references/citations in any format - we'll detect them automatically
                </div>
            </div>
        `,
        buttons: [{
            text: 'Check References',
            class: 'quaternary',
            callback: async () => {
                await startReferenceCheck(cardId);
            }
        }]
    });
}
```

### WebSocket Handlers

**New Message Types**:
- `reference_check_progress` - Progress updates during extraction/validation
- `reference_check_complete` - Results ready for preview

**Handler Registration** (in `routeMessage()` function, ~line 5680):
```javascript
// Add to special message type handling
case 'reference_check_progress':
    handleReferenceCheckProgress(data);
    break;
case 'reference_check_complete':
    handleReferenceCheckComplete(data);
    break;
```

**New Handler Functions**:
```javascript
function handleReferenceCheckProgress(data) {
    const cardId = referenceCheckState.cardId;
    const { current_step, status, progress_percent, claims_found,
            claims_validated, total_claims } = data;

    updateThinkingProgress(cardId, progress_percent, status);

    // Show intermediate results
    if (current_step === 1 && claims_found) {
        showClaimsFoundBox(cardId, claims_found);
    }

    if (current_step === 2 && claims_validated) {
        updateValidationProgress(cardId, claims_validated, total_claims);
    }
}

function handleReferenceCheckComplete(data) {
    const cardId = referenceCheckState.cardId;
    const { validation_results, csv_s3_key, total_claims,
            claims_validated } = data;

    completeThinkingInCard(cardId);

    // Auto-trigger preview (no button needed)
    setTimeout(() => {
        autoTriggerReferenceCheckPreview(
            cardId,
            validation_results,
            csv_s3_key
        );
    }, 1500);
}
```

---

## API Specification

### Actions

#### 1. startReferenceCheck
**Request**:
```json
{
    "action": "startReferenceCheck",
    "email": "user@example.com",
    "session_id": "sess_123",
    "submitted_text": "Text with claims and references..."
}
```

**Response** (immediate - success):
```json
{
    "status": "queued",
    "conversation_id": "refcheck_abc123",
    "message": "Reference check started. Results will be sent via WebSocket."
}
```

**Response** (immediate - text too large):
```json
{
    "status": "error",
    "error": "text_too_large",
    "message": "Text is too large to process. Please limit to 24,000 words or less.",
    "details": {
        "word_count": 35000,
        "estimated_tokens": 46550,
        "max_words": 24000,
        "max_tokens": 32000
    }
}
```

#### 2. getReferenceCheckResults
**Request**:
```json
{
    "action": "getReferenceCheckResults",
    "conversation_id": "refcheck_abc123",
    "session_id": "sess_123"
}
```

**Response**:
```json
{
    "status": "complete",
    "validation_results": [...],
    "csv_s3_key": "s3://bucket/path/results.csv",
    "download_url": "https://..."
}
```

---

## WebSocket Messages

### 1. Extraction Progress
```json
{
    "type": "reference_check_progress",
    "conversation_id": "refcheck_abc123",
    "current_step": 0,
    "total_steps": 2,
    "status": "Analyzing text and extracting claims...",
    "progress_percent": 25,
    "phase": "extraction"
}
```

### 2. Claims Found
```json
{
    "type": "reference_check_progress",
    "conversation_id": "refcheck_abc123",
    "current_step": 1,
    "total_steps": 2,
    "status": "Found 8 claims (5 with references, 3 without)",
    "progress_percent": 35,
    "phase": "extraction",
    "claims_found": 8,
    "claims_with_refs": 5,
    "claims_without_refs": 3
}
```

### 3. Validation Progress
```json
{
    "type": "reference_check_progress",
    "conversation_id": "refcheck_abc123",
    "current_step": 2,
    "total_steps": 2,
    "status": "Validating claim 3 of 8...",
    "progress_percent": 60,
    "phase": "validation",
    "claims_validated": 3,
    "total_claims": 8
}
```

### 4. Completion
```json
{
    "type": "reference_check_complete",
    "conversation_id": "refcheck_abc123",
    "phase": "complete",
    "status": "Validation complete! Found 8 claims.",
    "total_claims": 8,
    "claims_validated": 8,
    "validation_results": [
        {
            "claim_id": "claim_001",
            "statement": "AI models can hallucinate facts",
            "context": "Studies show that...",
            "reference": "[Johnson, A. (2023)]",
            "reference_description": "Research paper on AI hallucinations",
            "reference_says": "The paper confirms that...",
            "support_level": "strongly_supported"
        }
    ],
    "csv_s3_key": "reference_checks/user@example.com/sess_123/refcheck_abc123/results.csv"
}
```

### 5. Unsuitable Text
```json
{
    "type": "reference_check_progress",
    "conversation_id": "refcheck_abc123",
    "current_step": 0,
    "status": "This text doesn't contain verifiable claims or references. Please provide text with specific statements that can be fact-checked.",
    "progress_percent": 100,
    "phase": "unsuitable",
    "unsuitable": true,
    "reason": "No specific claims detected",
    "suggestion": "Try pasting AI-generated content with references, or scientific text with citations."
}
```

---

## Implementation Phases

### Phase 1: Backend Infrastructure (Current)
- [ ] Create folder structure
- [ ] Set up action routing
- [ ] Implement conversation management
- [ ] Create basic pipeline orchestration
- [ ] Add WebSocket message sending

### Phase 2: Claim Extraction (Step 0)
- [ ] Write claim extraction prompt
- [ ] Implement claim_extractor.py
- [ ] Test with sample texts
- [ ] Handle unsuitable text cases
- [ ] Parse reference formats

### Phase 3: Reference Validation (Step 1)
- [ ] Write validation prompts
- [ ] Implement reference_validator.py
- [ ] Implement fact_checker.py
- [ ] Test with real references
- [ ] Handle inaccessible references

### Phase 4: Results Compilation (Step 2)
- [ ] Implement result_compiler.py
- [ ] Generate CSV format
- [ ] Save to S3
- [ ] Test download flow

### Phase 5: Frontend Integration
- [ ] Modify Get Started card
- [ ] Create Reference Check card
- [ ] Add WebSocket handlers
- [ ] Implement progress indicators
- [ ] Test auto-preview trigger

### Phase 6: Testing & Refinement
- [ ] End-to-end testing
- [ ] Error handling
- [ ] Cost optimization
- [ ] User feedback integration

### Future Enhancements
- [ ] Text mapping (highlight claims in original text)
- [ ] Iterative refinement (user can refine results)
- [ ] Batch processing (multiple documents)
- [ ] Export formats (PDF, JSON, etc.)
- [ ] Citation format detection (APA, MLA, Chicago, etc.)

---

## Configuration

### reference_check_config.json
```json
{
    "text_limits": {
        "max_tokens": 32000,
        "max_words": 24000,
        "tokens_per_word": 1.33
    },
    "extraction": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 16000,
        "temperature": 0.3,
        "min_claims": 1,
        "max_claims": 50
    },
    "validation": {
        "model": "claude-haiku-4-5",
        "max_tokens": 8000,
        "temperature": 0.2,
        "max_parallel_validations": 5,
        "timeout_seconds": 60,
        "max_web_searches": 3
    },
    "support_levels": [
        "strongly_supported",
        "supported",
        "partially_supported",
        "unclear",
        "contradicted",
        "inaccessible"
    ]
}
```

---

## Cost Estimates

**Per reference check (estimated)**:
- Claim extraction: $0.02-0.05 (SONNET 4.5, one call)
- Reference validation: $0.01-0.03 per claim (Haiku + web search)
- For 10 claims: ~$0.15-0.35 total
- For 50 claims: ~$0.60-1.50 total

**Optimization strategies**:
- Use Haiku for validation (cheaper than Sonnet)
- Parallel validation (faster, same cost)
- Cache validation results for same references
- Early return for unsuitable text (save costs)

---

## Notes

- This design follows the Table Maker pattern closely for consistency
- Auto-preview simplifies user flow (no configuration needed)
- Support levels are more nuanced than binary true/false
- Text mapping feature deferred to future phase
- Early return prevents wasted processing on unsuitable text
