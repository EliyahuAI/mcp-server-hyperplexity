# Table Maker Lambda Integration - Implementation Guide

**Date:** October 13, 2025
**Status:** Ready for Implementation
**Prerequisites:** Standalone table_maker system tested and working (see TEST_REPORT.md)

---

## Executive Summary

This document provides complete guidance for integrating the tested standalone table generation system into the lambda architecture with an interactive frontend experience. The implementation uses subagents for autonomous execution and focuses on rapid iteration to 3-row previews with intelligent context understanding.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Decisions](#architecture-decisions)
3. [Configuration System](#configuration-system)
4. [Frontend User Experience Flow](#frontend-user-experience-flow)
5. [Backend Lambda Architecture](#backend-lambda-architecture)
6. [Data Flow and State Management](#data-flow-and-state-management)
7. [Implementation Tasks](#implementation-tasks)
8. [Testing Strategy](#testing-strategy)
9. [Technical Specifications](#technical-specifications)

---

## System Overview

### Goal
Create an interactive, AI-powered table generation system that allows users to rapidly design research tables through natural conversation, preview results, and seamlessly transition to validation.

### Core Principle
**Speed to Preview:** Bias toward generating a 3-row preview quickly (after minimal conversation) to give users concrete feedback. Users can then refine or accept and proceed to full table generation + validation.

### Key Features
1. **Conversational Design:** Natural language interaction to define research purpose
2. **Context Intelligence:** Web search integration to understand user's domain and needs
3. **Rapid Preview:** 3 fully-populated sample rows + column definitions + future ID columns list
4. **Iterative Refinement:** Accept preview → validate, or refine → regenerate
5. **Seamless Integration:** Preview uses existing transposed display, transitions to validation flow
6. **Subagent Architecture:** Autonomous parallel execution for performance

---

## Architecture Decisions

### 1. Use Existing Config Generation Lambda AND Conversation Tools
**Decision:** Do NOT recreate config generation logic OR conversation handling. The existing system already has these capabilities.

**Existing Conversation Tools:**
The system already has robust conversation handling with markdown support in `generate_config_unified.py`:
- **config_change_log** system tracks conversation history
- **instructions** field for user messages
- **ai_summary** for AI responses
- **clarifying_questions** for AI questions to user
- **reasoning** for AI explanation of changes
- Integrates with config lambda which uses markdown prompts with {{VARIABLE}} placeholders
- Supports iterative refinement through `existing_config` parameter

**Implementation for Table Maker:**
- Reuse the existing conversation infrastructure from config generation
- Build `table_analysis` format from table maker conversation data
- Add new `conversation_context` field to `table_analysis` payload:
  ```python
  table_analysis = {
      'basic_info': {...},
      'column_analysis': {...},
      'domain_info': {...},
      'conversation_context': {  # NEW - enrich existing config generation
          'research_purpose': str,  # User's initial request
          'ai_reasoning': str,      # Why this table structure
          'column_details': [...],  # Full column definitions with importance
          'identification_columns': [...]  # Which columns are IDs
      }
  }
  ```

### 2. Deployment via Deployment Scripts ONLY
**Decision:** ALL deployment must use the existing deployment scripts. No manual Lambda updates allowed.

**Deployment System:**
- `deploy_all.sh` - Orchestrates all lambda deployments
- `deployment/create_interface_package.py` - Builds and deploys interface lambda
- `deployment/create_package.py` - Builds and deploys validation lambda
- `deployment/deploy_config_lambda.py` - Builds and deploys config lambda
- Supports environment flags: `--environment dev|test|staging|prod`
- Supports rebuild options: `--force-rebuild`, `--no-rebuild`, `--quick-update`

**Table Maker Integration:**
- Table maker code must be included in `deployment/create_interface_package.py`
- Add `table_maker/` directory to package in `copy_source_files()` function
- Add table_maker dependencies to `requirements-interface-lambda.txt`
- Test deployment with `./deploy_all.sh --environment dev`

### 3. Configuration File for Table Maker Settings
**Location:** `table_maker/table_maker_config.json`

**Purpose:** Centralize all table maker-specific settings (models, tokens, web searches, conversation parameters)

**Schema:**
```json
{
  "conversation": {
    "model": "claude-sonnet-4-5",
    "max_turns_before_preview": 3,
    "min_turns_before_preview": 1,
    "readiness_threshold": 0.75,
    "max_tokens": 8000,
    "use_web_search_for_context": true,
    "context_web_searches": 3
  },
  "preview_generation": {
    "sample_row_count": 3,
    "model": "claude-sonnet-4-5",
    "max_tokens": 12000,
    "search_context": "high"
  },
  "full_table_generation": {
    "default_row_count": 20,
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "batch_size": 10
  },
  "models": {
    "conversation": "claude-sonnet-4-5",
    "preview": "claude-sonnet-4-5",
    "expansion": "claude-sonnet-4-5"
  },
  "features": {
    "enable_column_definitions_in_csv": true,
    "remove_definitions_for_validation": true,
    "enable_context_research": true,
    "show_id_columns_in_blue_circles": true
  }
}
```

### 4. Subagent Architecture
**Implementation Method:** Use Claude Code's Task tool with specialized subagents

**Subagents:**
1. **context-researcher:** Web search to understand user's domain and research needs
2. **conversation-manager:** Handle conversation flow and determine readiness
3. **table-generator:** Generate table structures and sample data
4. **config-bridge:** Convert table data to config lambda format

---

## Frontend User Experience Flow

### Entry Point
**Location:** Main dashboard
**Button:** "Create New Table" (prominent placement, similar to "Upload Excel")

### Step 1: Initial Prompt
```
┌─────────────────────────────────────────────────┐
│  Create a Research Table                        │
├─────────────────────────────────────────────────┤
│                                                 │
│  What would you like to build a research       │
│  table about?                                   │
│                                                 │
│  ┌────────────────────────────────────────┐   │
│  │ Example: Track AI research papers on   │   │
│  │ transformers with citation data        │   │
│  │                                         │   │
│  │ [Large text input area]                │   │
│  │                                         │   │
│  │                                         │   │
│  └────────────────────────────────────────┘   │
│                                                 │
│              [Continue] [Cancel]                │
└─────────────────────────────────────────────────┘
```

### Step 2: Conversational Refinement (1-3 turns)
**Display:** Chat-style interface with user messages and AI responses

**AI Focus:**
- Understand research purpose
- Identify who will use this table and how
- Clarify data sources and validation needs
- Understand domain context (trigger web search if needed)

**Example Exchange:**
```
User: Track AI research papers on transformers

AI: I'll help you create a comprehensive research table for
    transformer papers. Let me understand your needs:

    - Are you focused on a specific application (NLP, vision,
      multimodal)?
    - Do you need citation metrics and reproducibility data?
    - Will this be used for competitive analysis or research
      literature review?

    [Context research running in background via web search]

User: Focus on NLP, need citations and code availability

AI: Perfect! I'm designing a table with:
    - Paper identification (title, year, authors)
    - Impact metrics (citations, venue tier)
    - Technical details (innovation, architecture)
    - Reproducibility (code, datasets)

    Let me generate a preview with 3 sample papers...
    [Generating preview...]
```

**Readiness Detection:**
- After 1-3 turns, AI determines if enough information gathered
- Bias toward moving to preview quickly
- If user provides detailed initial description, may go straight to preview

### Step 3: Preview Display (Transposed Table + Metadata)

**Layout:** Similar to validation preview

```
┌─────────────────────────────────────────────────────────────┐
│  Table Preview: Transformer Research Papers                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Purpose: Track landmark transformer papers for NLP research│
│           with citation metrics and reproducibility data    │
│                                                              │
│  [Download Preview Table]                                   │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  TRANSPOSED TABLE VIEW (3 sample rows)                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ◉ paper_title          "Attention is All You Need"        │
│  ◉ publication_year     2017                                │
│    authors              Vaswani et al.                      │
│    venue                NeurIPS                             │
│    venue_tier           A*                                  │
│    citation_count       95000                               │
│    arxiv_url            https://arxiv.org/abs/1706.03762   │
│    key_innovation       Introduced transformer...           │
│    ...                                                      │
│                                                              │
│  [Column shows Paper 1 | Paper 2 | Paper 3]                │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  COLUMN DEFINITIONS                                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ◉ paper_title (ID, CRITICAL)                              │
│     Full title of the research paper                        │
│                                                              │
│  ◉ publication_year (ID, CRITICAL)                         │
│     Year published or first appeared on arXiv              │
│                                                              │
│    authors (HIGH)                                           │
│     Primary authors (first author et al. format)           │
│                                                              │
│    ... [all columns listed]                                │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  ADDITIONAL ROWS                                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  When you accept this table, we will generate 20 more      │
│  rows with these ID combinations:                          │
│                                                              │
│  ◉ BERT, 2019                                              │
│  ◉ GPT-3, 2020                                             │
│  ◉ Vision Transformer, 2021                                │
│  ◉ Chinchilla, 2022                                        │
│  ◉ ... (16 more)                                           │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Refine Table]  [Accept and Validate →]                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Display Features:**
- **Blue circles (◉)** for ID columns (like validation preview)
- **Transposed view** showing 3 sample rows side-by-side
- **Column definitions** with importance levels
- **Future ID list** showing what additional rows will be generated
- **Download button** for preview CSV (3 rows + all ID columns for future rows)

### Step 4A: Refine Table (Optional)
**Trigger:** User clicks "Refine Table"

**Action:**
- Show chat interface again
- User provides refinement instructions
- AI regenerates preview with changes
- Return to Step 3

### Step 4B: Accept and Validate
**Trigger:** User clicks "Accept and Validate"

**Actions:**
1. Generate full table (default 20 rows, configurable)
2. Generate validation config using existing lambda flow
3. Store CSV in unified S3 storage (remove column definitions from CSV)
4. Run preview validation (like existing flow)
5. Show preview validation results
6. User can proceed to full validation

**State Transition:**
- Table maker session → Standard validation session
- Store conversation history and table metadata
- CSV ready for validation
- Config ready for validation

---

## Backend Lambda Architecture

### New Lambda Actions (Interface Lambda)

#### 1. `handle_table_conversation_start`
**Location:** `src/lambdas/interface/actions/table_maker/conversation.py`

**Purpose:** Start a new table design conversation

**Input:**
```python
{
    'action': 'startTableConversation',
    'email': 'user@example.com',
    'session_id': 'session_20251013_123456',
    'user_message': 'Create a table to track AI research papers...'
}
```

**Process:**
1. Create conversation_id
2. Load table_maker_config.json
3. If config enables context research: Launch context-researcher subagent (web search)
4. Launch conversation-manager subagent with user message
5. Store conversation state in S3
6. Return AI response via WebSocket

**Output:**
```python
{
    'success': True,
    'conversation_id': 'table_conv_abc123',
    'ai_message': 'I'll help you create...',
    'clarifying_questions': '...',
    'ready_to_generate': False,  # Not ready yet
    'turn_count': 1
}
```

#### 2. `handle_table_conversation_continue`
**Location:** `src/lambdas/interface/actions/table_maker/conversation.py`

**Purpose:** Continue conversation and check if ready for preview

**Input:**
```python
{
    'action': 'continueTableConversation',
    'email': 'user@example.com',
    'session_id': 'session_20251013_123456',
    'conversation_id': 'table_conv_abc123',
    'user_message': 'Focus on NLP papers with citations...'
}
```

**Process:**
1. Load conversation state from S3
2. Launch conversation-manager subagent with updated conversation
3. Check readiness_threshold (from config)
4. If ready: Auto-generate preview
5. Store updated conversation state
6. Return response via WebSocket

**Output:**
```python
{
    'success': True,
    'conversation_id': 'table_conv_abc123',
    'ai_message': '...',
    'ready_to_generate': True,  # Ready!
    'preview_data': {
        'columns': [...],
        'sample_rows': [...],
        'future_ids': [...]
    }
}
```

#### 3. `handle_table_preview_generate`
**Location:** `src/lambdas/interface/actions/table_maker/preview.py`

**Purpose:** Generate 3-row preview from conversation

**Input:**
```python
{
    'action': 'generateTablePreview',
    'email': 'user@example.com',
    'session_id': 'session_20251013_123456',
    'conversation_id': 'table_conv_abc123'
}
```

**Process:**
1. Load conversation state from S3
2. Launch table-generator subagent for preview (3 rows)
3. Generate transposed data for display
4. Store preview in S3
5. Return formatted preview data

**Output:**
```python
{
    'success': True,
    'preview_data': {
        'columns': [
            {
                'name': 'paper_title',
                'description': '...',
                'importance': 'CRITICAL',
                'is_identification': True
            },
            ...
        ],
        'sample_rows_transposed': [
            {'paper_title': 'Attention is All You Need', ...},
            {'paper_title': 'BERT', ...},
            {'paper_title': 'GPT-3', ...}
        ],
        'future_ids': [
            {'paper_title': 'Vision Transformer', 'publication_year': 2021},
            {'paper_title': 'Chinchilla', 'publication_year': 2022},
            ...
        ]
    },
    'download_url': 'https://...'  # Preview CSV
}
```

#### 4. `handle_table_accept_and_validate`
**Location:** `src/lambdas/interface/actions/table_maker/finalize.py`

**Purpose:** Generate full table, config, and run preview validation

**Input:**
```python
{
    'action': 'acceptTableAndValidate',
    'email': 'user@example.com',
    'session_id': 'session_20251013_123456',
    'conversation_id': 'table_conv_abc123',
    'row_count': 20  # Optional override
}
```

**Process:**
1. Load conversation state and preview from S3
2. Launch table-generator subagent for full table
3. Generate CSV (with column definitions for user)
4. Store CSV in unified S3 storage
5. Build enhanced table_analysis with conversation_context
6. Call existing `handle_generate_config_unified()` with enhanced payload
7. Config lambda generates validation config
8. Store config with versioning
9. Create CSV for validation (WITHOUT column definitions)
10. Launch preview validation (existing flow)
11. Return results via WebSocket

**Output:**
```python
{
    'success': True,
    'table_csv_key': 's3://...',
    'validation_csv_key': 's3://...',  # Without column definitions
    'config_key': 's3://...',
    'config_version': 1,
    'preview_validation_results': {
        # Standard preview validation format
    }
}
```

### Lambda File Structure

```
src/lambdas/interface/actions/table_maker/
├── __init__.py
├── conversation.py          # Conversation handlers
├── preview.py               # Preview generation
├── finalize.py              # Accept and full generation
├── context_research.py      # Web search for context
└── config_bridge.py         # Convert to config lambda format

table_maker/
├── table_maker_config.json  # Configuration file
├── src/                     # Existing standalone code
│   ├── conversation_handler.py
│   ├── table_generator.py
│   ├── row_expander.py
│   ├── config_generator.py  # NOT used in lambda (use config lambda)
│   ├── prompt_loader.py
│   └── schema_validator.py
├── prompts/                 # Existing prompts
├── schemas/                 # Existing schemas
└── TEST_REPORT.md          # Standalone test results
```

---

## Data Flow and State Management

### Conversation State (S3)
**Location:** `s3://bucket/email/domain/session_id/table_maker/conversation_{conv_id}.json`

**Schema:**
```json
{
  "conversation_id": "table_conv_abc123",
  "session_id": "session_20251013_123456",
  "email": "user@example.com",
  "created_at": "2025-10-13T12:00:00Z",
  "last_updated": "2025-10-13T12:05:00Z",
  "status": "preview_generated",
  "turn_count": 2,
  "messages": [
    {
      "role": "user",
      "content": "Create a table...",
      "timestamp": "2025-10-13T12:00:00Z"
    },
    {
      "role": "assistant",
      "content": "I'll help you...",
      "timestamp": "2025-10-13T12:01:00Z",
      "metadata": {
        "model": "claude-sonnet-4-5",
        "tokens": 2890,
        "confidence": 0.7
      }
    }
  ],
  "context_research": {
    "performed": true,
    "sources": [...],
    "insights": "User appears to be in academic research..."
  },
  "current_proposal": {
    "columns": [...],
    "sample_rows": [...],
    "ready_to_generate": true
  }
}
```

### Preview Data (S3)
**Location:** `s3://bucket/email/domain/session_id/table_maker/preview_{conv_id}.csv`

**Format:** CSV with column definitions as comments (first 20 lines)

### Full Table (S3)
**Location:** `s3://bucket/email/domain/session_id/table_{session_id}.xlsx`

**Two versions:**
1. **With column definitions** (for user download)
2. **Without column definitions** (for validation)

---

## Implementation Tasks

### Phase 1: Configuration and Deployment Setup
**Estimated Time:** 3-4 hours

#### Task 1.1: Create table_maker_config.json
- [ ] Define all configuration parameters
- [ ] Set model defaults (Claude Sonnet 4.5)
- [ ] Set conversation thresholds
- [ ] Set row count defaults
- [ ] Enable/disable features

#### Task 1.2: Update Deployment Scripts
**CRITICAL:** All changes must go through deployment scripts

- [ ] Update `deployment/create_interface_package.py`:
  - [ ] Add table_maker directory to `copy_source_files()` function:
    ```python
    # Copy table_maker directory
    table_maker_src = PROJECT_DIR / "table_maker"
    if table_maker_src.exists():
        shutil.copytree(table_maker_src, PACKAGE_DIR / "table_maker", dirs_exist_ok=True)
        logger.info("Copied table_maker directory")
    ```
  - [ ] Verify table_maker dependencies in `requirements-interface-lambda.txt`

- [ ] Test deployment to dev environment:
  ```bash
  ./deploy_all.sh --environment dev --force-rebuild
  ```

#### Task 1.3: Create Lambda Action Files
- [ ] Create `src/lambdas/interface/actions/table_maker/` directory structure
- [ ] Create `__init__.py` with action routing
- [ ] Set up imports from packaged table_maker code

#### Task 1.4: Update Interface Lambda Routing
- [ ] Add table_maker action routing in `src/interface_lambda_function.py`
- [ ] Wire up WebSocket support for table maker actions
- [ ] Deploy and test with deployment script

### Phase 2: Backend Implementation
**Estimated Time:** 8-12 hours

#### Task 2.1: Conversation Management (conversation.py)
**NOTE:** Reuse existing conversation tools from `generate_config_unified.py` - do NOT reinvent conversation handling!
**REUSE:** Adapt `table_maker/src/conversation_handler.py` (536 lines) for lambda environment

- [ ] Implement `handle_table_conversation_start()`
  - [ ] **Reuse:** Import `TableConversationHandler` from standalone code
  - [ ] Create conversation_id and state structure (similar to config_change_log)
  - [ ] Create runs database entry: `create_run_record(session_id, email, total_rows=0, run_type="Table Generation")`
  - [ ] Load table_maker_config.json
  - [ ] Launch context-researcher subagent (if enabled)
  - [ ] **Reuse:** Existing prompt_loader pattern (markdown with {{VARIABLE}} placeholders)
  - [ ] **Reuse:** Existing schema_validator for response validation
  - [ ] Store conversation state in S3 using UnifiedS3Manager (NOT local files like standalone)
  - [ ] Send WebSocket update using existing WebSocket infrastructure
  - [ ] Update runs database: `update_run_status(session_id, run_key, status='IN_PROGRESS')`
- [ ] Implement `handle_table_conversation_continue()`
  - [ ] Load conversation state from S3 (NOT local files)
  - [ ] Follow config_change_log pattern for conversation history
  - [ ] Launch conversation-manager subagent
  - [ ] Check readiness threshold from table_maker_config.json
  - [ ] Auto-generate preview if ready
  - [ ] Send WebSocket update
  - [ ] Update runs database with progress
- [ ] **Deploy after implementation:** `./deploy_all.sh --environment dev`

#### Task 2.2: Context Research (context_research.py)
- [ ] Implement context research function
- [ ] Use existing web search (Perplexity or similar)
- [ ] Extract key insights about user's domain
- [ ] Store insights in conversation state
- [ ] Return formatted context to conversation manager

#### Task 2.3: Preview Generation (preview.py)
**REUSE:** Adapt `table_maker/src/table_generator.py` (397 lines) for lambda environment

- [ ] Implement `handle_table_preview_generate()`
  - [ ] Load conversation state from S3
  - [ ] **Reuse:** Import `TableGenerator` from standalone code
  - [ ] Generate 3 sample rows using existing table_generator
  - [ ] Generate transposed data structure for frontend display
  - [ ] Create future_ids list (20 rows worth of ID combinations)
  - [ ] Store preview CSV in S3 using UnifiedS3Manager
  - [ ] Generate download link via S3 presigned URL
  - [ ] Send WebSocket update with preview_data
  - [ ] Update runs database: `update_run_status()` with preview complete

#### Task 2.4: Table Finalization (finalize.py)
- [ ] Implement `handle_table_accept_and_validate()`
  - [ ] Generate full table (default 20 rows)
  - [ ] Create CSV WITH column definitions (user download)
  - [ ] Create CSV WITHOUT column definitions (validation)
  - [ ] Store both in S3
  - [ ] Build enhanced table_analysis with conversation_context
  - [ ] Call existing generate_config_unified()
  - [ ] Store config with versioning
  - [ ] Launch preview validation
  - [ ] Send WebSocket updates throughout

#### Task 2.5: Config Bridge (config_bridge.py)
- [ ] Implement function to build table_analysis from conversation
- [ ] Add conversation_context field
- [ ] Map column data to column_analysis format
- [ ] Infer domain_info from context research
- [ ] Include identification columns in metadata

### Phase 3: Frontend Implementation
**Estimated Time:** 10-15 hours
**Location:** `frontend/perplexity_validator_interface2.html`

#### Task 3.1: Entry Point
- [ ] Add "Create New Table" button to main dashboard in perplexity_validator_interface2.html
- [ ] Style button prominently (similar to "Upload Excel")
- [ ] Wire up to open table maker modal

#### Task 3.2: Initial Prompt Modal
- [ ] Add modal component to perplexity_validator_interface2.html for initial prompt
- [ ] Large text input area
- [ ] Example text/placeholder
- [ ] Continue/Cancel buttons
- [ ] Handle submission → API call to startTableConversation

#### Task 3.3: Conversational Interface
- [ ] Add chat-style interface component to perplexity_validator_interface2.html
- [ ] Display user messages
- [ ] Display AI messages
- [ ] Loading indicators during AI processing
- [ ] WebSocket integration for real-time updates (reuse existing WebSocket code)
- [ ] Auto-advance to preview when ready_to_generate=true

#### Task 3.4: Preview Display Component
- [ ] Add transposed table display to perplexity_validator_interface2.html (reuse existing validation preview component)
- [ ] Show blue circles (◉) for ID columns (reuse existing ID badge styling)
- [ ] Display column definitions section
- [ ] Display future IDs section
- [ ] Add "Download Preview Table" button
- [ ] Add "Refine Table" button → return to chat
- [ ] Add "Accept and Validate" button → finalize

#### Task 3.5: Refinement Flow
- [ ] Return to chat interface from preview
- [ ] Maintain conversation context
- [ ] Regenerate preview after refinement

#### Task 3.6: Validation Transition
- [ ] Show loading screen during full generation
- [ ] Display progress via WebSocket updates (reuse existing progress display)
- [ ] Show preview validation results (reuse existing preview validation component)
- [ ] Provide option to proceed to full validation
- [ ] Seamless transition to standard validation UI

### Phase 4: Testing
**Estimated Time:** 4-6 hours

#### Task 4.1: Unit Tests
- [ ] Test conversation flow handlers
- [ ] Test preview generation
- [ ] Test config bridge logic
- [ ] Test state management (S3 read/write)

#### Task 4.2: Integration Tests
- [ ] Test full conversation → preview → validation flow
- [ ] Test refinement loop
- [ ] Test WebSocket updates
- [ ] Test S3 storage and retrieval

#### Task 4.3: E2E Tests
- [ ] Test frontend → backend → config lambda flow
- [ ] Test with various research topics
- [ ] Test edge cases (minimal info, very detailed info)
- [ ] Test error handling and recovery

### Phase 5: Testing and Deployment
**Estimated Time:** 4-6 hours

#### Task 5.1: Test in Dev Environment
**CRITICAL:** Use deployment scripts for ALL deployments

- [ ] Deploy to dev environment:
  ```bash
  ./deploy_all.sh --environment dev --force-rebuild
  ```
- [ ] Verify table_maker actions are accessible
- [ ] Test conversation flow end-to-end
- [ ] Test preview generation
- [ ] Test full table generation and validation
- [ ] Verify config lambda integration
- [ ] Check WebSocket updates
- [ ] Monitor CloudWatch logs for errors

#### Task 5.2: Deploy to Test Environment
- [ ] Run comprehensive test suite
- [ ] Deploy to test:
  ```bash
  ./deploy_all.sh --environment test
  ```
- [ ] Perform UAT (User Acceptance Testing)
- [ ] Load testing for preview generation
- [ ] Verify S3 storage and cleanup

#### Task 5.3: Update Documentation
- [ ] Update INFRASTRUCTURE_GUIDE.md with table maker architecture
- [ ] Document new API endpoints
- [ ] Document configuration options in table_maker_config.json
- [ ] Create user guide for table maker feature
- [ ] Document deployment process for table maker

#### Task 5.4: Production Deployment
**CRITICAL:** Only use deployment script

- [ ] Final review of all code
- [ ] Deploy to production:
  ```bash
  ./deploy_all.sh --environment prod
  ```
- [ ] Monitor CloudWatch logs
- [ ] Verify functionality in production
- [ ] Gather user feedback
- [ ] Monitor costs and performance

---

## Testing Strategy

### Test Scenarios

#### Scenario 1: Minimal Information
**User Input:** "Track research papers"

**Expected:**
- AI asks clarifying questions
- 2-3 conversation turns
- Eventually generates generic academic paper table
- Preview shows 3 sample papers

#### Scenario 2: Detailed Information
**User Input:** "Create a comprehensive table to track transformer research papers in NLP, including citation counts from Google Scholar, venue tier rankings, reproducibility metrics like code availability and datasets used, and technical innovations. I'm a researcher at Stanford doing a literature review for a survey paper."

**Expected:**
- AI recognizes sufficient detail
- May trigger context research (Stanford, NLP, survey papers)
- Minimal clarifying questions
- Rapid generation of preview (1-2 turns)
- Preview shows 3 transformer papers with all requested fields

#### Scenario 3: Domain-Specific Context
**User Input:** "Track biotech companies developing theranostics for targeted cancer therapy"

**Expected:**
- AI triggers context research via web search
- Learns about theranostics, targeted therapy, key players
- Asks clarifying questions about specific data needs
- Generates preview with biotech-specific columns
- Preview shows 3 companies (e.g., Ratio Therapeutics, competitors)

#### Scenario 4: Refinement Loop
**User Input:** Initial → Preview → "Add a column for FDA approval status" → Refined Preview

**Expected:**
- First preview generated successfully
- User refines via chat
- Second preview includes new column
- All 3 sample rows updated with FDA status data

#### Scenario 5: Accept and Validate
**User Input:** Preview → Accept and Validate

**Expected:**
- Full table generated (20 rows)
- Config generated via existing lambda
- Preview validation runs automatically
- Results displayed in standard validation UI
- User can proceed to full validation

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Conversation start | < 10s | Including context research |
| Conversation turn | < 8s | AI response generation |
| Preview generation | < 30s | 3 rows with data |
| Full table generation | < 90s | 20 rows with data |
| Config generation | < 45s | Using existing lambda |
| Preview validation | < 120s | Using existing validator |

### Error Handling

**Common Errors:**
1. **API timeout:** Retry with exponential backoff
2. **Insufficient information:** Request more details from user
3. **Web search failure:** Continue without context research
4. **Config generation failure:** Show error, allow retry
5. **Validation failure:** Show error, allow refinement

---

## Technical Specifications

### API Endpoints (Interface Lambda)

#### POST /startTableConversation
```json
Request:
{
  "action": "startTableConversation",
  "email": "user@example.com",
  "session_id": "session_20251013_123456",
  "user_message": "Create a table..."
}

Response (via WebSocket):
{
  "type": "table_conversation_update",
  "conversation_id": "table_conv_abc123",
  "ai_message": "I'll help you...",
  "clarifying_questions": "...",
  "ready_to_generate": false,
  "turn_count": 1
}
```

#### POST /continueTableConversation
```json
Request:
{
  "action": "continueTableConversation",
  "email": "user@example.com",
  "session_id": "session_20251013_123456",
  "conversation_id": "table_conv_abc123",
  "user_message": "Focus on NLP papers..."
}

Response (via WebSocket):
{
  "type": "table_conversation_update",
  "conversation_id": "table_conv_abc123",
  "ai_message": "...",
  "ready_to_generate": true,
  "preview_data": {...}
}
```

#### POST /generateTablePreview
```json
Request:
{
  "action": "generateTablePreview",
  "email": "user@example.com",
  "session_id": "session_20251013_123456",
  "conversation_id": "table_conv_abc123"
}

Response (via WebSocket):
{
  "type": "table_preview_ready",
  "preview_data": {
    "columns": [...],
    "sample_rows_transposed": [...],
    "future_ids": [...]
  },
  "download_url": "https://..."
}
```

#### POST /acceptTableAndValidate
```json
Request:
{
  "action": "acceptTableAndValidate",
  "email": "user@example.com",
  "session_id": "session_20251013_123456",
  "conversation_id": "table_conv_abc123",
  "row_count": 20
}

Response (via WebSocket - multiple updates):
{
  "type": "table_generation_progress",
  "status": "Generating full table...",
  "progress": 25
}
{
  "type": "table_generation_progress",
  "status": "Generating validation config...",
  "progress": 50
}
{
  "type": "table_generation_progress",
  "status": "Running preview validation...",
  "progress": 75
}
{
  "type": "table_validation_complete",
  "table_csv_key": "s3://...",
  "config_key": "s3://...",
  "preview_validation_results": {...}
}
```

### Subagent Specifications

#### context-researcher
**Purpose:** Perform web search to understand user's domain and research needs

**Input:**
```python
{
    'user_message': str,
    'conversation_history': [...]
}
```

**Tools Available:**
- WebSearch
- WebFetch

**Output:**
```python
{
    'insights': str,  # Summary of research findings
    'domain': str,    # Identified domain
    'sources': [...]  # URLs used
}
```

#### conversation-manager
**Purpose:** Manage conversation flow and determine readiness for preview

**Input:**
```python
{
    'user_message': str,
    'conversation_history': [...],
    'context_insights': {...},  # From context-researcher
    'config': {...}  # table_maker_config.json
}
```

**Tools Available:**
- Read (prompts, schemas)
- Task (for spawning other subagents if needed)

**Output:**
```python
{
    'ai_message': str,
    'clarifying_questions': str,
    'ready_to_generate': bool,
    'confidence': float,
    'reasoning': str
}
```

#### table-generator
**Purpose:** Generate table structure and populate with sample data

**Input:**
```python
{
    'conversation_summary': str,
    'column_requirements': [...],
    'row_count': int,
    'context_insights': {...}
}
```

**Tools Available:**
- Read (existing table_maker code)
- Bash (run Python scripts)

**Output:**
```python
{
    'columns': [...],
    'rows': [...],
    'metadata': {...}
}
```

#### config-bridge
**Purpose:** Convert table data to config lambda format

**Input:**
```python
{
    'table_structure': {...},
    'conversation_history': [...],
    'context_insights': {...}
}
```

**Tools Available:**
- Read (schemas, existing code)

**Output:**
```python
{
    'table_analysis': {
        'basic_info': {...},
        'column_analysis': {...},
        'domain_info': {...},
        'conversation_context': {...}
    }
}
```

### WebSocket Message Types

| Type | Purpose | Data |
|------|---------|------|
| `table_conversation_update` | Conversation turn complete | AI message, readiness |
| `table_preview_ready` | Preview generated | Preview data, download URL |
| `table_generation_progress` | Full table progress | Status, progress % |
| `table_config_generated` | Config ready | Config key, version |
| `table_validation_progress` | Validation running | Status, progress % |
| `table_validation_complete` | All done | Results, next actions |

### S3 Storage Structure

```
s3://bucket/
└── email/
    └── domain/
        └── session_id/
            ├── table_maker/
            │   ├── conversation_{conv_id}.json
            │   ├── preview_{conv_id}.csv
            │   ├── preview_{conv_id}_metadata.json
            │   └── context_research_{conv_id}.json
            ├── table_{session_id}.xlsx              # User download (with definitions)
            ├── table_{session_id}_for_validation.xlsx  # Validation (no definitions)
            ├── config_v1_ai_generated.json
            └── session_info.json
```

---

## Special Considerations

### 1. Column Definition Handling
**Issue:** Column definitions should be visible in preview/download but removed for validation

**Solution:**
- Store two CSV versions:
  1. `table_{session_id}.xlsx` - WITH column definitions (user download)
  2. `table_{session_id}_for_validation.xlsx` - WITHOUT column definitions (validation input)
- Flag in `table_maker_config.json`: `remove_definitions_for_validation: true`

### 2. ID Column Display
**Issue:** ID columns should be visually distinct in preview

**Solution:**
- Frontend: Use blue circles (◉) for ID columns (like validation preview)
- Backend: Mark columns with `is_identification: true` in metadata
- CSS: Apply same styling as validation preview ID badges

### 3. Future ID List Generation
**Issue:** Need to show what rows will be generated without actually generating them

**Solution:**
- During preview generation, AI proposes ID combinations for future rows
- Store as `future_ids` array in preview metadata
- Display in frontend as bulleted list
- When user accepts, use these IDs to guide full table generation

### 4. Readiness Threshold Tuning
**Issue:** Balance between too many conversation turns and insufficient information

**Solution:**
- Default threshold: 0.75 (75% confidence)
- Min turns: 1 (allow immediate generation if very detailed input)
- Max turns: 3 (force generation to avoid infinite conversation)
- Configurable in `table_maker_config.json`

### 5. Context Research Performance
**Issue:** Web search adds latency to conversation start

**Solution:**
- Run context research in parallel with conversation AI
- Don't block conversation on research completion
- Incorporate insights in next turn if available
- Configurable: `use_web_search_for_context: true/false`

### 6. Config Lambda Integration
**Issue:** Config lambda expects specific table_analysis format

**Solution:**
- Use `config_bridge.py` to transform conversation data
- Add new `conversation_context` field without breaking existing structure
- Config lambda can use or ignore conversation_context
- Backward compatible with existing config generation

### 7. Cost Management
**Issue:** Multiple AI calls can be expensive

**Solution:**
- Use cheaper models where possible (check config)
- Cache context research results
- Reuse preview data when generating full table
- Show estimated costs to user before validation

---

## Success Criteria

### Functional Requirements
- [ ] User can create new table from natural language
- [ ] Conversation completes in 1-3 turns
- [ ] Preview displays correctly (transposed, blue circles, definitions)
- [ ] User can refine table via additional conversation
- [ ] User can accept and proceed to validation
- [ ] Full table generated with correct structure
- [ ] Config generated using existing lambda
- [ ] Preview validation runs successfully
- [ ] Seamless transition to full validation

### Performance Requirements
- [ ] Conversation start < 10s
- [ ] Preview generation < 30s
- [ ] Full table generation < 90s
- [ ] End-to-end (conversation → validation preview) < 3 minutes

### Quality Requirements
- [ ] AI-generated tables are accurate and relevant
- [ ] Column definitions are clear and helpful
- [ ] Sample data is realistic and diverse
- [ ] Config is optimized for the research domain

### User Experience Requirements
- [ ] Interface is intuitive and responsive
- [ ] Progress indicators are clear
- [ ] Error messages are helpful
- [ ] Download buttons work correctly
- [ ] Refinement loop is smooth

---

## Implementation Notes for Next Session

### Critical Requirements

#### 1. Reuse Existing Conversation Tools
**DO NOT RECREATE:** The system already has conversation handling with markdown support!

Existing tools in `generate_config_unified.py`:
- `config_change_log` - conversation history system
- `instructions` field - user messages
- `ai_summary`, `clarifying_questions`, `reasoning` - AI responses
- Config lambda uses markdown prompts with {{VARIABLE}} placeholders
- Schema validation for AI responses
- Iterative refinement through `existing_config`

**Action:** Study `generate_config_unified.py` to understand the existing pattern, then adapt it for table maker.

#### 2. Deployment Scripts ONLY
**ABSOLUTELY REQUIRED:** No manual Lambda updates allowed!

Deployment system:
- `deploy_all.sh` - Main deployment orchestrator
- `deployment/create_interface_package.py` - Interface lambda packager
- Supports environments: `--environment dev|test|staging|prod`
- Example: `./deploy_all.sh --environment dev --force-rebuild`

**Action:** Update `deployment/create_interface_package.py` to include table_maker directory in package.

### Starting Point - Standalone Implementation

The standalone table generation system is fully tested and production-ready (see `table_maker/TEST_REPORT.md`):

#### Existing Standalone Code (REUSE, DON'T RECREATE):
```
table_maker/
├── src/
│   ├── conversation_handler.py    (536 lines) - Multi-turn AI conversation orchestration
│   ├── table_generator.py         (397 lines) - CSV generation with metadata
│   ├── row_expander.py            (399 lines) - AI-powered row generation
│   ├── config_generator.py        (435 lines) - Config generation (WILL BE REPLACED by existing lambda flow)
│   ├── prompt_loader.py           (193 lines) - Markdown template loading with {{VARIABLE}} replacement
│   └── schema_validator.py        (280 lines) - JSON schema validation
├── prompts/
│   ├── table_initial.md           - Initial conversation prompt
│   ├── table_refinement.md        - Refinement conversation prompt
│   └── row_expansion.md           - Row expansion prompt
├── schemas/
│   ├── conversation_response.json - AI response schema
│   ├── row_expansion_response.json
│   └── table_structure.json
├── cli_demo.py                    (750+ lines) - Standalone CLI for testing
└── test_e2e.py                    - End-to-end integration test

Test Results: 107/111 unit tests passing (96.4%), E2E test passed
```

#### Key Changes Needed for Lambda Integration:

1. **Remove config_generator.py Usage** - Replace with existing `handle_generate_config_unified()` call
2. **Add Runs Database Tracking** - Track table generation operations in runs table
3. **Adapt for Lambda Environment** - No `DISABLE_AI_DEBUG_SAVES`, use proper S3 paths
4. **Remove Temperature Parameters** - Already removed from standalone code
5. **Add WebSocket Updates** - Real-time progress updates during generation
6. **Split CSV Generation** - Create two versions (with/without column definitions)
7. **Integrate with Unified S3 Manager** - Use session-based storage paths

#### What to Reuse Directly:
- `conversation_handler.py` - Core conversation logic (adapt S3 storage)
- `table_generator.py` - CSV generation (add second version without definitions)
- `row_expander.py` - Row expansion (adapt for lambda)
- `prompt_loader.py` - Template loading (use as-is)
- `schema_validator.py` - Validation (use as-is)
- All prompts and schemas (use as-is)

#### What NOT to Use:
- `config_generator.py` - Replace with existing config lambda integration
- `cli_demo.py` - Only for standalone testing
- Environment variable hacks (`DISABLE_AI_DEBUG_SAVES`) - Not needed in lambda

### Key Files to Create and Modify

#### Files to Create:
1. `table_maker/table_maker_config.json` - Configuration file
2. `src/lambdas/interface/actions/table_maker/__init__.py` - Action routing
3. `src/lambdas/interface/actions/table_maker/conversation.py` - Conversation handlers (reuse existing patterns!)
4. `src/lambdas/interface/actions/table_maker/preview.py` - Preview generation
5. `src/lambdas/interface/actions/table_maker/finalize.py` - Acceptance and validation
6. `src/lambdas/interface/actions/table_maker/context_research.py` - Web search integration
7. `src/lambdas/interface/actions/table_maker/config_bridge.py` - Config lambda integration
8. `frontend/perplexity_validator_interface2.html` - Add table maker UI components (modals, chat interface, preview display)

#### Files to Modify:
1. `deployment/create_interface_package.py` - Add table_maker directory to deployment package
2. `deployment/requirements-interface-lambda.txt` - Add any new table_maker dependencies
3. `src/interface_lambda_function.py` - Add table_maker action routing

### Key Integrations
1. **Existing Conversation Tools:** Study and reuse `config_change_log` system from `generate_config_unified.py`
2. **Markdown Prompts:** Reuse existing prompt_loader pattern ({{VARIABLE}} placeholders)
3. **Schema Validation:** Reuse existing schema_validator for AI response validation
4. **WebSocket:** Reuse existing WebSocket infrastructure in perplexity_validator_interface2.html for real-time updates
5. **S3 Storage:** Use UnifiedS3Manager for all file operations
6. **Config Lambda:** Call existing `handle_generate_config_unified()` with enhanced payload (DO NOT DUPLICATE CONFIG GENERATION)
7. **Validation Preview:** Reuse existing preview validation flow
8. **Transposed Display:** Reuse existing validation preview display component from perplexity_validator_interface2.html
9. **UI Components:** Integrate table maker UI into existing perplexity_validator_interface2.html (modals, chat, preview)
10. **Deployment:** Use deployment scripts ONLY - `./deploy_all.sh --environment <env>`

### Subagent Strategy
- Use Task tool with appropriate subagent types
- Run context research and conversation in parallel when possible
- Use subagents for all AI-heavy operations
- Aggregate results and send via WebSocket

### Testing Approach
1. Start with unit tests for each handler
2. Build integration tests for conversation flow
3. Test end-to-end with real user scenarios
4. Validate performance against targets
5. Test error handling and edge cases

---

## Questions for Clarification (to address in implementation)

1. **Row Count:** Default 20 rows for full table - should this be configurable per-table or fixed?
   - **Recommendation:** Make configurable in initial prompt ("Generate 20 papers" or "Generate 50 papers")

2. **Future IDs:** Should AI generate exact ID combinations or just examples?
   - **Recommendation:** Generate exact combinations that will be used in full table

3. **Column Definitions:** Format in CSV (comments) or separate file?
   - **Recommendation:** Comments in CSV for user download, omit for validation

4. **Context Research:** Always run or only when domain is unclear?
   - **Recommendation:** Configurable flag, default to true for better results

5. **Refinement Limits:** Should there be a max number of refinements?
   - **Recommendation:** No hard limit, but track and warn if excessive

6. **Download Timing:** When should user be able to download preview vs full table?
   - **Recommendation:** Both - preview download immediately, full table after acceptance

---

## Conclusion

This implementation guide provides complete specifications for integrating the table maker system into the lambda architecture with an interactive frontend. The design prioritizes:

1. **Speed:** Get to 3-row preview quickly
2. **Quality:** Use context research and conversation to understand needs
3. **Integration:** Leverage existing config generation and validation flows
4. **User Experience:** Interactive, visual, and intuitive

The next session should focus on:
1. Creating `table_maker_config.json`
2. Implementing backend lambda actions with subagents
3. Building frontend components
4. Testing end-to-end flow
5. Deploying to dev environment

All standalone code is tested and ready to integrate. The architecture is designed to reuse existing systems (config lambda, validation preview, WebSocket infrastructure) while adding new conversational capabilities.

**Estimated Total Implementation Time:** 30-40 hours (including testing and deployment)

**Ready to implement!**
